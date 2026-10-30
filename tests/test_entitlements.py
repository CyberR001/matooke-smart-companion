"""Membership: the promise that safety information stays free must be testable."""

from __future__ import annotations

from app.engine import entitlements as ent


def test_free_tier_keeps_every_safety_critical_capability():
    for feature in ent.SAFETY_CRITICAL:
        assert ent.allowed("basic_farmer", feature) is True, feature


def test_farm_doctor_advice_is_never_paywalled():
    assert ent.allowed("basic_farmer", "farm_doctor_advice")
    assert ent.allowed("basic_farmer", "disease_prevention_info")
    assert ent.allowed("basic_farmer", "bxw_outbreak_alert")


def test_premium_features_are_actually_gated():
    assert not ent.allowed("basic_farmer", "price_alerts")
    assert ent.allowed("smart_farmer", "price_alerts")
    assert not ent.allowed("smart_farmer", "business_reports")
    assert ent.allowed("professional_farmer", "business_reports")
    assert not ent.allowed("smart_farmer", "bulk_order_tools")
    assert ent.allowed("buyer_institution", "bulk_order_tools")


def test_gate_note_repeats_the_free_information_promise():
    note = ent.gate_note("basic_farmer", "price_alerts")
    assert "paid tier" in note
    assert "stay free" in note


def test_upsell_names_the_cheapest_tier_that_unlocks_the_feature():
    upsell = ent.upsell_for("basic_farmer", "business_reports")
    assert upsell["show"] is True
    assert upsell["tier"] == "professional_farmer"
    assert "validated with farmers" in upsell["message"]
    assert ent.upsell_for("professional_farmer", "business_reports") == {"show": False}


def test_unknown_features_are_allowed_rather_than_blocked():
    """Fail-open: an unlisted feature must not lock a farmer out of advice."""
    assert ent.allowed("basic_farmer", "some_new_free_tool") is True
    assert ent.is_gated("some_new_free_tool") is False


def test_tier_matrix_marks_prices_as_hypotheses():
    rows = ent.tier_matrix()
    assert len(rows) == 4
    assert all(r["price_is_hypothesis"] for r in rows)
    assert rows[0]["key"] == "basic_farmer" and rows[0]["price_ugx_month"] == 0
