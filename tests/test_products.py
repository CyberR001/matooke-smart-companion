"""Value addition: yield and margin arithmetic, assumptions vs measurements."""

from __future__ import annotations

import pytest

from app.engine import products

TRIAL = {
    "trial_date": "2026-09-01",
    "fresh_input_kg": 100.0,
    "output_kg": 20.0,
    "processing_hours": 30.0,
    "labour_ugx": 75000,
    "energy_ugx": 9000,
    "packaging_ugx": 18000,
    "transport_ugx": 10000,
    "spoilage_pct": 0.0,
    "selling_price_ugx_per_kg": 6000,
    "fresh_price_ugx_per_kg": 500,
}


def test_yield_is_output_over_input_times_hundred():
    econ = products.estimate_economics("matooke_flour", fresh_kg=200.0)
    assert econ.output_kg == pytest.approx(200.0 * econ.yield_pct / 100.0, abs=0.05)
    assert econ.yield_pct == products.product_spec("matooke_flour")["yield_pct"]


def test_margin_is_revenue_minus_direct_costs():
    econ = products.estimate_economics("dried_matooke_chips", fresh_kg=100.0)
    assert econ.revenue_ugx == int(econ.output_kg * econ.selling_price_ugx_per_kg)
    assert econ.margin_ugx == econ.revenue_ugx - econ.costs.total
    assert econ.costs.raw_material == int(
        100.0 * products.catalog()["cost_basis"]["fresh_matooke_ugx_per_kg"]
    )


def test_target_output_back_solves_the_fresh_weight_needed():
    econ = products.estimate_economics("matooke_flour", target_output_kg=50.0)
    assert econ.output_kg == pytest.approx(50.0, abs=0.6)
    assert econ.fresh_kg > 50.0  # flour loses most of its weight to water and peel


def test_measured_trial_overrides_the_catalog_assumption():
    assumed = products.estimate_economics("matooke_flour", fresh_kg=100.0)
    measured = products.estimate_economics("matooke_flour", fresh_kg=100.0, trial=TRIAL)
    assert assumed.source == "assumed"
    assert measured.source == "measured"
    assert measured.yield_pct == pytest.approx(20.0, abs=0.1)
    assert measured.yield_pct != assumed.yield_pct
    assert any("trial" in n.lower() for n in measured.notes)


def test_assumed_results_advertise_that_they_need_a_trial():
    econ = products.estimate_economics("matooke_crisps", fresh_kg=100.0)
    assert econ.source == "assumed"
    assert any("trial" in n.lower() for n in econ.notes)


def test_ranking_returns_every_product_with_explainable_contributions():
    recs = products.rank_products(fresh_kg=500.0, available_services={"dryer"})
    assert len(recs) == len(products.product_keys())
    for r in recs:
        assert abs(sum(r.contributions.values()) - r.score) < 0.005
        assert r.reasons
        assert r.verdict in {"worth a trial batch", "possible, needs checks", "not yet attractive"}
    assert [r.score for r in recs] == sorted([r.score for r in recs], reverse=True)


def test_hub_pull_lifts_the_product_the_hub_is_actually_buying():
    without = products.rank_products(fresh_kg=400.0)
    with_hub = products.rank_products(fresh_kg=400.0, hub_buying_keys={"matooke_crisps"})

    def score(recs, key):
        return next(r.score for r in recs if r.product_key == key)

    assert score(with_hub, "matooke_crisps") > score(without, "matooke_crisps")
    assert any("Hub" in " ".join(r.reasons) for r in with_hub if r.product_key == "matooke_crisps")


def test_missing_equipment_reduces_feasibility():
    with_dryer = products.rank_products(fresh_kg=400.0, available_services={"dryer", "mill"})
    without = products.rank_products(fresh_kg=400.0, available_services=set())

    def flour(recs):
        return next(r for r in recs if r.product_key == "matooke_flour")

    assert flour(with_dryer).score > flour(without).score
    assert any("Missing" in reason for reason in flour(without).reasons)


def test_negative_margin_is_reported_rather_than_hidden():
    calc = products.fresh_kg_needed_for_income("parboiled_frozen_matooke", 400000)
    econ = products.estimate_economics("parboiled_frozen_matooke", fresh_kg=100.0)
    if econ.margin_ugx <= 0:
        assert calc["possible"] is False
        assert "loses money" in calc["reason"]
    else:
        assert calc["possible"] is True
        assert calc["expected_margin_ugx"] > 0


def test_income_target_scales_monotonically():
    small = products.fresh_kg_needed_for_income("matooke_flour", 200000)
    large = products.fresh_kg_needed_for_income("matooke_flour", 600000)
    assert small["possible"] and large["possible"]
    assert large["fresh_kg_needed"] > small["fresh_kg_needed"]
    assert large["fresh_kg_needed"] == pytest.approx(small["fresh_kg_needed"] * 3, rel=0.05)


def test_spoilage_is_applied_to_output_weight():
    clean = products.estimate_economics("dried_matooke_chips", fresh_kg=100.0)
    dirty = products.estimate_economics(
        "dried_matooke_chips", fresh_kg=100.0, trial={**TRIAL, "spoilage_pct": 20.0}
    )
    assert dirty.output_kg < clean.output_kg
    assert dirty.spoilage_pct == pytest.approx(20.0)


def test_break_even_needs_a_contribution_to_be_positive():
    econ = products.estimate_economics("matooke_flour", fresh_kg=100.0, trial=TRIAL, fixed_costs_ugx=100000)
    if econ.margin_ugx > 0:
        assert econ.break_even_output_kg and econ.break_even_output_kg > 0
