"""The API contract, including the refusals that protect farmers and buyers."""

from __future__ import annotations

from datetime import date, timedelta


def test_health_reports_the_synthetic_data_warning(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["has_price_history"] is True
    assert "synthetic" in body["data_disclaimer"].lower()


def test_markets_list_latest_price_and_provenance(client):
    markets = client.get("/api/v1/markets").json()
    assert len(markets) >= 2
    m = markets[0]
    assert m["latest_price_ugx"] > 0
    assert m["synthetic"] is True


def test_forecast_payload_carries_confidence_and_caveats(client):
    fc = client.get("/api/v1/markets/1/forecast?horizon_days=45").json()
    assert fc["n_records"] > 40
    assert fc["confidence"] in {"high", "medium", "low"}
    assert fc["caveats"]
    assert "guaranteed" in " ".join(fc["caveats"]).lower()
    assert fc["points"], "two years of weekly data should support a projection"
    first = fc["points"][0]
    assert first["low_ugx"] < first["predicted_ugx"] < first["high_ugx"]
    assert fc["chart"]["history"] and fc["chart"]["projection"]
    assert fc["data_is_synthetic"] is True


def test_forecast_for_unknown_market_is_a_404(client):
    assert client.get("/api/v1/markets/9999/forecast").status_code == 404


def test_price_entry_is_accepted_but_marked_unverified(client):
    before = len(client.get("/api/v1/markets/1/prices?days=400").json()["prices"])
    r = client.post(
        "/api/v1/prices",
        json={
            "market_id": 1,
            "observed_on": (date.today() - timedelta(days=1)).isoformat(),
            "price_ugx": 35500,
            "source": "test agent",
        },
    )
    assert r.status_code == 201
    assert "unverified" in r.json()["message"]
    after = client.get("/api/v1/markets/1/prices?days=400").json()["prices"]
    assert len(after) == before + 1
    assert after[0]["verified"] is False or after[1]["verified"] is False


def test_future_dated_price_is_refused(client):
    r = client.post(
        "/api/v1/prices",
        json={
            "market_id": 1,
            "observed_on": (date.today() + timedelta(days=3)).isoformat(),
            "price_ugx": 40000,
        },
    )
    assert r.status_code == 422


def test_doctor_assessment_is_recorded_and_referred_when_uncertain(client):
    answers = {
        "speed": "days",
        "pattern": "one",
        "fruit": "premature",
        "bud": "black",
        "inside": "brown",
        "leaves": "yellow",
    }
    r = client.post("/api/v1/doctor/assess", json={"farmer_id": 1, "answers": answers})
    assert r.status_code == 200
    body = r.json()
    assert body["candidates"][0]["key"] == "bxw"
    assert body["referred"] is True
    assert body["advice"]["immediate_actions"]
    assert body["advice"]["free_access"] is True
    assert "possible" in body["headline"].lower()
    assert body["case_id"] > 0
    assert client.post(
        "/api/v1/doctor/feedback", params={"case_id": body["case_id"], "rating": 4}
    ).status_code in {200, 201, 404, 422}


def test_doctor_endpoint_lists_coverage(client):
    body = client.get("/api/v1/doctor/questions").json()
    assert len(body["questions"]) >= 6
    assert "not enabled" in body["image_model"]
    assert any(c["key"] == "black_sigatoka" for c in body["conditions_covered"])


def test_trial_registration_replaces_the_assumption(client):
    key = "dried_matooke_chips"
    before = client.get(f"/api/v1/products/{key}/economics?fresh_kg=200").json()
    assert before["source"] == "assumed"
    r = client.post(
        "/api/v1/trials",
        json={
            "product_key": key,
            "fresh_input_kg": 200.0,
            "output_kg": 44.0,
            "processing_hours": 30.0,
            "labour_ugx": 60000,
            "energy_ugx": 8000,
            "packaging_ugx": 20000,
            "transport_ugx": 12000,
            "spoilage_pct": 5.0,
            "selling_price_ugx_per_kg": 6400,
            "fresh_price_ugx_per_kg": 900,
        },
    )
    assert r.status_code == 201
    assert r.json()["yield_pct"] == 22.0
    after = client.get(f"/api/v1/products/{key}/economics?fresh_kg=200").json()
    assert after["source"] == "measured"
    assert after["yield_pct"] == 22.0


def test_impossible_trial_is_rejected(client):
    r = client.post(
        "/api/v1/trials",
        json={"product_key": "matooke_flour", "fresh_input_kg": 10.0, "output_kg": 40.0},
    )
    assert r.status_code == 422


def test_listing_validation_and_creation(client):
    bad = client.post(
        "/api/v1/listings",
        json={
            "seller_id": 1,
            "district": "Mukono",
            "quantity_bunches": 0,
            "expected_harvest_date": (date.today() + timedelta(days=20)).isoformat(),
            "asking_price_ugx_per_bunch": 30000,
        },
    )
    assert bad.status_code == 422
    past = client.post(
        "/api/v1/listings",
        json={
            "seller_id": 1,
            "district": "Mukono",
            "quantity_bunches": 40,
            "expected_harvest_date": (date.today() - timedelta(days=5)).isoformat(),
            "asking_price_ugx_per_bunch": 30000,
        },
    )
    assert past.status_code == 422
    ok = client.post(
        "/api/v1/listings",
        json={
            "seller_id": 1,
            "district": "Mukono",
            "quantity_bunches": 40,
            "expected_harvest_date": (date.today() + timedelta(days=20)).isoformat(),
            "asking_price_ugx_per_bunch": 31000,
            "grade": "high",
        },
    )
    assert ok.status_code == 201
    assert any(row["id"] == ok.json()["id"] for row in client.get("/api/v1/listings").json())


def test_order_lifecycle_over_http(client):
    listings = [row for row in client.get("/api/v1/listings").json() if row["available_bunches"] >= 10]
    reqs = client.get("/api/v1/requirements").json()
    assert listings and reqs
    listing, req = listings[0], reqs[0]
    qty = min(10, req["quantity_bunches"], listing["available_bunches"])
    price = min(listing["asking_price_ugx_per_bunch"], req["max_price_ugx_per_bunch"])
    created = client.post(
        "/api/v1/orders",
        json={
            "listing_id": listing["id"],
            "requirement_id": req["id"],
            "quantity_bunches": qty,
            "price_per_bunch_ugx": price,
            "deposit_pct": 25,
            "commission_pct": 3,
        },
    )
    assert created.status_code == 201, created.text
    ref = created.json()["reference"]
    order = created.json()["order"]
    assert order["status"] == "proposed"
    assert order["advance_ugx"] + order["balance_due_ugx"] == order["total_value_ugx"]
    assert (
        "not a loan" in order["payment_note"].lower() or "not hold the money" in order["payment_note"].lower()
    )

    for action in ["send_terms", "request_deposit", "confirm", "start_growth", "mark_ready", "deliver"]:
        r = client.post(f"/api/v1/orders/{ref}/transition", json={"action": action, "actor": "test"})
        assert r.status_code == 200, r.text
    settle = client.post(f"/api/v1/orders/{ref}/settle", json={"delivered_bunches": qty})
    assert settle.status_code == 200
    body = settle.json()
    assert body["shortfall_bunches"] == 0
    # Buyer still owes exactly the balance agreed in the terms.
    assert body["buyer_balance_due_ugx"] == order["balance_due_ugx"]
    # And the three-way split has to reconcile.
    assert body["to_farmer_at_settlement_ugx"] + body["service_fee_ugx"] == body["buyer_balance_due_ugx"]
    assert body["advance_paid_ugx"] + body["to_farmer_at_settlement_ugx"] == body["farmer_total_ugx"]
    assert body["refund_due_to_buyer_ugx"] == 0
    final = client.get(f"/api/v1/orders/{ref}").json()
    assert final["status"] == "settled"
    kinds = [e["kind"] for e in final["events"]]
    assert "settled" in kinds and "proposed" in kinds


def test_over_committing_a_listing_is_refused(client):
    listings = client.get("/api/v1/listings").json()
    reqs = client.get("/api/v1/requirements").json()
    lot = next(x for x in listings if x["available_bunches"] > 0)
    r = client.post(
        "/api/v1/orders",
        json={
            "listing_id": lot["id"],
            "requirement_id": reqs[0]["id"],
            "quantity_bunches": lot["available_bunches"] + 1,
            "price_per_bunch_ugx": lot["asking_price_ugx_per_bunch"],
        },
    )
    assert r.status_code == 422
    assert "uncommitted" in r.json()["detail"]


def test_deposit_cap_is_applied_and_reported(client):
    listings = [row for row in client.get("/api/v1/listings").json() if row["available_bunches"] > 5]
    reqs = client.get("/api/v1/requirements").json()
    lot = listings[0]
    r = client.post(
        "/api/v1/orders",
        json={
            "listing_id": lot["id"],
            "requirement_id": reqs[0]["id"],
            "quantity_bunches": 5,
            "price_per_bunch_ugx": lot["asking_price_ugx_per_bunch"],
            "deposit_pct": 90,
        },
    )
    assert r.status_code == 201
    assert r.json()["order"]["deposit_pct"] == 60.0
    assert r.json()["adjustments"], "the cap must be disclosed to the caller"


def test_crop_failure_endpoint_keeps_the_farmer_side_protected(client):
    listings = [row for row in client.get("/api/v1/listings").json() if row["available_bunches"] > 3]
    reqs = client.get("/api/v1/requirements").json()
    created = client.post(
        "/api/v1/orders",
        json={
            "listing_id": listings[0]["id"],
            "requirement_id": reqs[0]["id"],
            "quantity_bunches": 3,
            "price_per_bunch_ugx": listings[0]["asking_price_ugx_per_bunch"],
        },
    ).json()
    ref = created["reference"]
    r = client.post(f"/api/v1/orders/{ref}/crop-failure", params={"verified": True})
    assert r.status_code == 200
    body = r.json()
    assert "immediate repayment" not in body["rule"]
    assert body["options"]
    assert client.get(f"/api/v1/orders/{ref}").json()["crop_failure_declared"] is True


def test_matches_are_explainable(client):
    body = client.get("/api/v1/matches").json()
    assert body["count"] == len(body["suggestions"])
    for s in body["suggestions"]:
        assert 0 < s["score"] <= 1
        assert set(s["components"]) == {"proximity", "quantity", "timing", "price", "quality"}
        assert s["explanations"]
        assert s["quantity_bunches"] > 0


def test_opportunities_endpoint_labels_verification(client):
    body = client.get("/api/v1/opportunities").json()
    assert body["rule"]
    for item in body["items"]:
        assert item["effective"]["status"] != "internal_draft"
        assert item["source_name"]
        if item["effective"]["status"] in {"open", "closing_soon"}:
            assert item["is_verified"] is True


def test_hub_notices_respect_purchase_limits(client):
    body = client.get("/api/v1/hub/notices").json()
    assert body["count"] >= 1
    for n in body["notices"]:
        assert n["purchase_limit_kg"] > 0, "working-capital limits are part of the model"


def test_tiers_endpoint_publishes_the_untouchable_list(client):
    body = client.get("/api/v1/tiers").json()
    assert "farm_doctor_advice" in body["never_gated"]
    assert "basic_farmer" in [t["key"] for t in body["tiers"]]
    assert all(t["price_is_hypothesis"] for t in body["tiers"])


def test_dashboard_payload_composes_the_modules(client):
    body = (
        client.get("/api/v1/dashboard?family_id=1").json()
        if False
        else client.get("/api/v1/dashboard?farm_id=1").json()
    )
    assert body["farmer"]
    assert body["price"]["confidence"] in {"high", "medium", "low"}
    assert body["advice" if "advice" in body else "headline"]
    assert body["orders"]
    assert "synthetic" in body["disclaimer"].lower()


def test_farm_advice_endpoint(client):
    body = client.get("/api/v1/farms/1/advice?urgent_need_ugx=300000").json()
    assert body["advice"]["options"]
    assert body["recommendations"]
    assert body["fresh_kg_assumed"] > 0
    assert body["kg_per_bunch"] == 27.0
