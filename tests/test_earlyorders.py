"""Early orders: the money maths and the state machine."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine import earlyorders as eo

TODAY = date(2026, 10, 30)


def terms(qty=100, price=30000, dep=25.0, comm=3.0):
    return eo.OrderTerms(
        quantity_bunches=qty, price_per_bunch_ugx=price, deposit_pct=dep, commission_pct=comm
    )


def test_money_always_adds_up():
    t = terms(qty=120, price=28000, dep=25.0, comm=3.0)
    assert t.total_value_ugx == 120 * 28000
    assert t.advance_ugx + t.balance_ugx == t.total_value_ugx
    assert t.farmer_net_ugx + t.service_fee_ugx == t.total_value_ugx
    assert t.service_fee_ugx == round(t.total_value_ugx * 0.03)


def test_zero_deposit_and_full_deposit_edges():
    assert terms(dep=0.0).advance_ugx == 0
    assert terms(dep=0.0).balance_ugx == terms(dep=0.0).total_value_ugx
    capped, notes = eo.normalise_terms(
        quantity_bunches=10, price_per_bunch_ugx=30000, deposit_pct=95.0, commission_pct=3.0
    )
    assert capped.deposit_pct == eo.MAX_DEPOSIT_PCT
    assert notes, "capping a deposit must be disclosed, not silent"


def test_commission_is_capped_and_disclosed():
    t, notes = eo.normalise_terms(
        quantity_bunches=10, price_per_bunch_ugx=30000, deposit_pct=25, commission_pct=40
    )
    assert t.commission_pct == 15.0
    assert any("capped" in n.lower() for n in notes)


def test_build_order_rejects_past_delivery():
    with pytest.raises(ValueError):
        eo.build_order(
            reference="X",
            listing_id=1,
            requirement_id=1,
            terms=terms(),
            delivery_date=TODAY - timedelta(days=1),
            today=TODAY,
        )


def test_build_order_refuses_spot_delivery_as_an_early_order():
    with pytest.raises(ValueError):
        eo.build_order(
            reference="X",
            listing_id=1,
            requirement_id=1,
            terms=terms(),
            delivery_date=TODAY + timedelta(days=2),
            harvest_estimate_confidence="medium",
            today=TODAY,
        )


def test_low_confidence_estimate_produces_a_warning_not_a_block():
    order = eo.build_order(
        reference="X",
        listing_id=1,
        requirement_id=1,
        terms=terms(),
        delivery_date=TODAY + timedelta(days=30),
        harvest_estimate_confidence="low",
        today=TODAY,
    )
    assert order["status"] == "proposed"
    assert order["terms_snapshot"]["warnings"], "unreliable estimate must be surfaced"


def test_state_machine_happy_path():
    status = "proposed"
    for action, expected in [
        ("send_terms", "terms_sent"),
        ("request_deposit", "awaiting_deposit"),
        ("confirm", "confirmed"),
        ("start_growth", "in_growth"),
        ("mark_ready", "ready_for_delivery"),
        ("deliver", "delivered"),
        ("settle", "settled"),
    ]:
        status, msg = eo.transition(status, action)
        assert status == expected, msg
    assert eo.TRANSITIONS["settled"] == set()


def test_cannot_settle_before_delivery():
    with pytest.raises(eo.InvalidTransition):
        eo.transition("in_growth", "settle")


def test_closed_order_cannot_move():
    with pytest.raises(eo.InvalidTransition):
        eo.transition("settled", "cancel")


def test_unknown_action_is_rejected():
    with pytest.raises(eo.InvalidTransition):
        eo.transition("proposed", "apply_loan")


def test_dispute_is_recoverable_to_settle_or_cancel():
    status, _ = eo.transition("delivered", "raise_dispute")
    assert status == "disputed"
    assert "settled" in eo.TRANSITIONS["disputed"] or "delivered" in eo.TRANSITIONS["disputed"]


def test_short_delivery_is_priced_for_what_was_supplied():
    t = terms(qty=100, price=30000, dep=25.0, comm=3.0)
    res = eo.settle(t, delivered_bunches=60, advance_paid_ugx=t.advance_ugx)
    assert res["supplied_value_ugx"] == 60 * 30000
    assert res["shortfall_bunches"] == 40
    assert res["service_fee_ugx"] == round(60 * 30000 * 0.03)
    # Buyer pays for what was delivered, minus what they already advanced.
    assert res["buyer_balance_due_ugx"] == 60 * 30000 - t.advance_ugx
    # Farmer keeps the delivered value less the fee, across advance + balance.
    assert res["farmer_total_ugx"] == 60 * 30000 - res["service_fee_ugx"]
    assert t.advance_ugx + res["to_farmer_at_settlement_ugx"] == res["farmer_total_ugx"]
    assert res["advance_to_reconcile_ugx"] == 0
    assert res["fee_netted_at_settlement"] is True


def test_settlement_never_leaves_the_farmer_owing_the_platform_invisibly():
    """Deposit larger than the delivered value: the fee cannot be netted out."""
    t = terms(qty=100, price=30000, dep=60.0, comm=3.0)
    res = eo.settle(t, delivered_bunches=1, advance_paid_ugx=t.advance_ugx)
    assert res["buyer_balance_due_ugx"] == 0
    assert res["refund_due_to_buyer_ugx"] > 0
    assert res["fee_netted_at_settlement"] is False
    assert any("not be netted" in line or "exceeds the value delivered" in line for line in res["lines"])


def test_full_delivery_settles_to_zero_shortfall_and_reports_every_party():
    t = terms(qty=40, price=35000, dep=25.0, comm=2.5)
    res = eo.settle(t, delivered_bunches=40, advance_paid_ugx=t.advance_ugx)
    assert res["shortfall_bunches"] == 0
    assert res["supplied_value_ugx"] == t.total_value_ugx
    assert res["to_farmer_at_settlement_ugx"] + res["service_fee_ugx"] == res["buyer_balance_due_ugx"]
    assert len(res["lines"]) >= 6


def test_heavy_shortfall_returns_excess_advance_rather_than_hiding_it():
    t = terms(qty=100, price=30000, dep=50.0, comm=3.0)
    res = eo.settle(t, delivered_bunches=10, advance_paid_ugx=t.advance_ugx)
    assert res["balance_due_ugx"] == 0
    assert res["advance_to_reconcile_ugx"] > 0
    assert any("exceeds" in line for line in res["lines"])


def test_crop_failure_offers_reschedule_not_collection():
    plan = eo.declare_crop_failure(order_status="in_growth", verified=False, days_to_delivery=21)
    assert any("revis" in o.lower() or "part" in o.lower() for o in plan["options"])
    assert "not an immediate repayment demand" in plan["rule"] or "does not" in plan["rule"]
    assert any("officer" in o.lower() for o in plan["options"])


def test_urgency_comparison_is_labelled_as_an_assumption():
    t = terms(qty=100, price=30000, dep=25.0, comm=3.0)
    res = eo.urgency_alternative(
        need_ugx=200000, order=t, spot_price_ugx_per_bunch=32000, months_to_harvest=1
    )
    assert res["advance_available_ugx"] == t.advance_ugx
    assert res["covers_need"] is True
    assert "assumption" in res["assumption"].lower()
    assert "verified" in res["assumption"].lower()
    assert res["price_forgone_ugx"] == 100 * (32000 - 30000)
    note = res["note"].lower()
    assert "advance" in note and "loan" in note
    assert "guarantee" not in note


def test_suggested_delivery_never_precedes_harvest():
    harvest = TODAY + timedelta(days=20)
    assert eo.suggest_delivery_date(harvest) > harvest


def test_no_interest_appears_anywhere_in_the_terms():
    t = terms()
    snapshot = eo.build_order(
        reference="X",
        listing_id=1,
        requirement_id=1,
        terms=t,
        delivery_date=TODAY + timedelta(days=30),
        today=TODAY,
    )
    text = str(snapshot).lower() + str(t).lower()
    assert "interest" not in text or "no interest" in text
    assert snapshot["terms_snapshot"]["payment_note"]
