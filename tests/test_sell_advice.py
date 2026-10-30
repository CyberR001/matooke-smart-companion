"""'When to sell': the recommendation rules and their guard rails."""

from __future__ import annotations

from datetime import date, timedelta

from app.engine.prices import PricePoint, forecast_prices
from app.engine.sell_advice import advise

START = date(2024, 1, 4)


def fc_for(month_effect: dict[int, float], horizon: int = 90):
    pts = []
    for i in range(104):
        d = START + timedelta(days=i * 7)
        pts.append(PricePoint(d, int(30000 * (1 + month_effect.get(d.month, 0.0))), verified=True))
    return forecast_prices(pts, horizon_days=horizon, step_days=7)


def options_by_key(advice):
    return {o.key: o for o in advice.options}


def test_weak_forecast_never_recommends_waiting():
    thin = forecast_prices(
        [PricePoint(START + timedelta(days=i * 7), 30000 + i * 40, verified=True) for i in range(6)]
    )
    advice = advise(thin, harvest_date=START + timedelta(days=800), quantity_bunches=80)
    assert advice.confidence == "low"
    assert advice.primary_option != "wait_to_harvest"
    assert advice.price_at_harvest_ugx is None
    assert any("record" in o.key or "record" in o.label.lower() for o in advice.options)


def test_projected_glut_steers_away_from_selling_everything_at_once():
    # Harvest in October, the weak month in this synthetic pattern.
    fc = fc_for({1: 0.20, 10: -0.22})
    harvest = date(2026, 10, 15)
    advice = advise(fc, harvest_date=harvest, quantity_bunches=100)
    opts = options_by_key(advice)
    triggers = (
        advice.price_at_harvest_ugx is not None
        and advice.expected_change_pct is not None
        and advice.expected_change_pct <= -8
        and advice.confidence != "low"
    )
    if triggers:
        alerts = " ".join(advice.alerts).lower()
        assert "oversupply" in alerts or "glut" in alerts
        assert advice.primary_option in {"early_order", "stage", "sell_now"}
        assert advice.primary_option != "wait_to_harvest"
    assert opts, "must always return at least one actionable option"


def test_firm_prices_can_justify_waiting_only_with_enough_evidence():
    fc = fc_for({1: 0.22, 7: -0.05})
    advice = advise(fc, harvest_date=date(2026, 1, 10), quantity_bunches=100, urgent_need_ugx=0)
    if advice.confidence == "low":
        assert advice.primary_option != "wait_to_harvest"
    elif (advice.expected_change_pct or 0) >= 8:
        assert advice.primary_option == "wait_to_harvest"
        assert any("range" in c.lower() or "not a guarantee" in c.lower() for c in advice.caveats)


def test_urgent_need_adds_a_cash_note_and_weights_certainty():
    fc = fc_for({1: 0.1, 10: -0.1})
    plain = advise(fc, harvest_date=date(2026, 10, 20), quantity_bunches=100)
    urgent = advise(fc, harvest_date=date(2026, 10, 20), quantity_bunches=100, urgent_need_ugx=900000)
    assert plain.urgent_need_note == ""
    assert "900,000" in urgent.urgent_need_note
    text = urgent.urgent_need_note.lower()
    # Must not read as a lending offer from MatookeSmart.
    assert "credit" in text
    assert "we lend" not in text and "we will pay" not in text
    assert any("certainty" in a for a in urgent.alerts)


def test_unmet_urgent_need_shows_the_gap_and_labels_the_loan_benchmark():
    fc = fc_for({1: 0.1, 10: -0.1})
    advice = advise(fc, harvest_date=date(2026, 10, 20), quantity_bunches=4, urgent_need_ugx=5000000)
    note = advice.urgent_need_note
    assert "leaving" in note, note
    assert "assumed" in note and "benchmark" in note
    assert "not as an offer from MatookeSmart" in note
    assert "10 % a month" in note  # the rate is flagged as an assumption


def test_pre_order_price_is_not_priced_above_the_spot_market():
    """A buyer's ceiling is a maximum, so a pre-order cannot look like free money."""
    fc = fc_for({1: 0.05, 10: -0.05})
    advice = advise(
        fc,
        harvest_date=date(2026, 10, 20),
        quantity_bunches=50,
        open_requirement_price_ugx=99999,  # absurd ceiling
    )
    opts = options_by_key(advice)
    pre = opts["early_order"]
    assert pre.expected_revenue_ugx <= 50 * fc.latest_price_ugx


def test_hub_notice_is_surfaced_as_an_option():
    fc = fc_for({10: -0.1})
    advice = advise(
        fc,
        harvest_date=date(2026, 10, 20),
        quantity_bunches=40,
        hub_buying_note="Hub is buying dried chips at 1,450 UGX/kg in Wakiso",
    )
    opts = options_by_key(advice)
    assert "value_addition" in opts
    assert "Hub is buying" in opts["value_addition"].detail


def test_split_lot_is_offered_only_when_the_lot_is_meaningful():
    fc = fc_for({10: -0.05})
    big = advise(fc, harvest_date=date(2026, 10, 20), quantity_bunches=60)
    small = advise(fc, harvest_date=date(2026, 10, 20), quantity_bunches=12)
    assert "stage" in options_by_key(big)
    assert "stage" not in options_by_key(small)


def test_every_option_states_a_certainty_label():
    fc = fc_for({1: 0.1})
    advice = advise(fc, harvest_date=date(2026, 1, 20), quantity_bunches=80, urgent_need_ugx=100000)
    for o in advice.options:
        assert o.certainty in {"certain now", "depends on forecast", "depends on fulfilment"}
    assert advice.primary_option in options_by_key(advice)


def test_advice_carries_the_limitations_text():
    fc = fc_for({1: 0.1})
    advice = advise(fc, harvest_date=date(2026, 1, 20), quantity_bunches=80)
    joined = " ".join(advice.caveats).lower()
    assert "not a guaranteed" in joined
    assert any("synthetic" in a.lower() for a in advice.alerts)
