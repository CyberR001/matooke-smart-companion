"""Screen-level checks: the four §16 screens render, and never overstate."""

from __future__ import annotations

PAGES = [
    "/",
    "/dashboard",
    "/farm-doctor",
    "/when-to-sell",
    "/marketplace",
    "/early-orders",
    "/opportunities",
    "/hub",
    "/prices",
    "/tiers",
]


def test_every_screen_renders(client):
    for path in PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "<svg" in r.text or path in {"/", "/tiers", "/prices"}, "expected mobile-first markup"


def test_synthetic_data_warning_appears_on_every_screen(client):
    for path in PAGES:
        body = client.get(path).text
        assert "synthetic" in body.lower(), f"{path} is missing the data warning"


def test_no_screen_promises_a_guaranteed_price(client):
    for path in [*PAGES, "/farm-doctor?speed=days&fruit=premature&bud=black"]:
        body = client.get(path).text.lower()
        assert "guaranteed price" not in body
        assert "will rise to" not in body
        assert "definitely" not in body


def test_dashboard_shows_the_decision_not_only_a_chart(client):
    body = client.get("/dashboard").text
    assert "Sell decision" in body
    assert "suggested route" in body
    assert "confidence" in body.lower()
    # The dashboard has to say, in words, that a pre-order is not credit.
    lowered = body.lower()
    assert "not credit" in lowered
    assert "does not lend" in lowered or "no medical" in lowered


def test_farm_doctor_marks_output_as_possible_and_refers(client):
    body = client.get(
        "/farm-doctor?speed=days&pattern=one&fruit=premature&bud=black&inside=brown&leaves=yellow"
    ).text
    assert "Possible" in body
    assert "referred for human assessment" in body
    assert "free to every farmer" in body


def test_farm_doctor_lists_an_immediate_action(client):
    body = client.get("/farm-doctor?speed=days&pattern=one&fruit=premature&bud=black").text
    assert "what to do now" in body.lower()
    # Tool disinfection and male-bud control are the two actions that matter for BXW.
    lowered = body.lower()
    assert "disinfect" in lowered or "bleach" in lowered
    assert "male bud" in lowered


def test_when_to_sell_shows_options_with_numbers_and_ranges(client):
    body = client.get("/when-to-sell?farm_id=1&horizon=60&quantity=80&urgent=250000").text
    assert "Your options, priced" in body
    assert "per bunch" in body
    assert "Watch out:" in body or "risks" in body.lower()
    assert "Model detail" in body  # method, MAPE and record count are inspectable


def test_hub_page_distinguishes_measured_from_assumed(client):
    body = client.get("/hub?fresh_kg=500").text
    assert "measured yield" in body or "assumed yield" in body
    assert "trial" in body.lower()
    assert "Hub buying requirements" in body


def test_marketplace_explains_each_match(client):
    body = client.get("/marketplace").text
    assert "Suggested matches" in body
    assert "proximity" in body.lower()
    assert "fit" in body.lower()


def test_opportunities_show_source_and_check_date(client):
    body = client.get("/opportunities").text
    assert "checked" in body.lower()
    assert "unverified" in body.lower() or "needs" in body.lower()


def test_tiers_page_states_what_stays_free(client):
    body = client.get("/tiers").text
    assert "Never gated" in body
    assert "hypotheses" in body.lower() or "validated" in body.lower()


def test_order_detail_renders_terms_and_events(client):
    orders = client.get("/api/v1/orders").json()
    assert orders
    body = client.get(f"/orders/{orders[0]['reference']}").text
    assert "Agreed terms" in body
    assert "Event log" in body
    assert "does not hold the money" in body or "authorised" in body.lower()


def test_unknown_farm_is_a_clean_404_rather_than_someone_elses_data(client):
    for path in ("/dashboard?farm_id=9999", "/when-to-sell?farm_id=9999"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert "farm" in r.text.lower() or "farm" in str(r.json()).lower()
    assert client.get("/orders/MS-EO-1999-9999").status_code == 404
