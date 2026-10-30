"""Buyer matching: scoring behaviour and capacity discipline."""

from __future__ import annotations

from datetime import date, timedelta

from app.engine import matching

TODAY = date(2026, 10, 30)


def listing(**kw):
    base = {
        "id": 1,
        "seller_name": "Aisha",
        "district": "Mukono",
        "quantity_bunches": 100,
        "committed_bunches": 0,
        "expected_harvest_date": TODAY + timedelta(days=14),
        "asking_price_ugx_per_bunch": 32000,
        "grade": "medium",
    }
    base.update(kw)
    return base


def requirement(**kw):
    base = {
        "id": 1,
        "organisation": "School",
        "district": "Kampala",
        "quantity_bunches": 60,
        "needed_by": TODAY + timedelta(days=16),
        "min_grade": "medium",
        "max_price_ugx_per_bunch": 34000,
        "is_recurring_weekly": False,
    }
    base.update(kw)
    return base


def test_closer_farmer_beats_farther_one():
    near = matching.score_pair(listing(district="Kampala"), requirement(), today=TODAY)
    far = matching.score_pair(listing(district="Gulu"), requirement(), today=TODAY)
    assert near.score > far.score
    assert near.components["proximity"] > far.components["proximity"]


def test_price_above_ceiling_kills_the_match():
    within = matching.score_pair(listing(), requirement(), today=TODAY)
    overpriced = matching.score_pair(listing(asking_price_ugx_per_bunch=60000), requirement(), today=TODAY)
    assert within.components["price"] == 1.0
    assert overpriced.components["price"] < 0.35
    assert overpriced.price_gap_ugx == 26000


def test_harvest_after_the_need_is_penalised():
    late = matching.score_pair(
        listing(expected_harvest_date=TODAY + timedelta(days=45)), requirement(), today=TODAY
    )
    on_time = matching.score_pair(listing(), requirement(), today=TODAY)
    assert late.components["timing"] < on_time.components["timing"]


def test_harvest_long_before_the_need_is_also_penalised():
    """Fresh matooke cannot sit for two months - both directions must hurt."""
    early = matching.score_pair(
        listing(expected_harvest_date=TODAY + timedelta(days=1)),
        requirement(needed_by=TODAY + timedelta(days=90)),
        today=TODAY,
    )
    assert early.components["timing"] < 0.5
    assert "will not keep" in early.timing_note


def test_grade_below_minimum_is_flagged_not_silently_accepted():
    weak = matching.score_pair(listing(grade="low"), requirement(min_grade="high"), today=TODAY)
    assert weak.components["quality"] == 0.4
    assert any("below the buyer" in e for e in weak.explanations)


def test_greedy_allocation_never_over_commits_a_listing():
    listings = [
        listing(id=1, quantity_bunches=50),
        listing(id=2, quantity_bunches=30, expected_harvest_date=TODAY + timedelta(days=10)),
    ]
    reqs = [
        requirement(id=1, quantity_bunches=60),
        requirement(id=2, quantity_bunches=25, needed_by=TODAY + timedelta(days=20)),
    ]
    sugg, leftovers = matching.match_all(listings, reqs, today=TODAY)
    allocated: dict[int, int] = {}
    for s in sugg:
        allocated[s["listing_id"]] = allocated.get(s["listing_id"], 0) + s["quantity_bunches"]
    assert allocated.get(1, 0) <= 50
    assert allocated.get(2, 0) <= 30
    assert sum(s["quantity_bunches"] for s in sugg) <= 80
    # All 80 available bunches were allocated, so the leftover must be unmet demand.
    assert not [row for row in leftovers if row["kind"] == "listing"]
    unmet = [row for row in leftovers if row["kind"] == "requirement"]
    assert sum(row["unmet_bunches"] for row in unmet) == 5


def test_matching_is_deterministic():
    listings = [
        listing(id=i, quantity_bunches=40, district=d)
        for i, d in enumerate(["Mukono", "Kampala", "Masaka"], start=1)
    ]
    reqs = [
        requirement(id=i, quantity_bunches=30, district=d)
        for i, d in enumerate(["Kampala", "Masaka"], start=1)
    ]
    a, _ = matching.match_all(listings, reqs, today=TODAY)
    b, _ = matching.match_all(listings, reqs, today=TODAY)
    assert [(s["listing_id"], s["requirement_id"], s["quantity_bunches"]) for s in a] == [
        (s["listing_id"], s["requirement_id"], s["quantity_bunches"]) for s in b
    ]


def test_distance_uses_coordinates_when_available():
    same_district_far_apart = listing(district="Kampala", latitude=0.30, longitude=32.60)
    scores = matching.score_pair(
        same_district_far_apart, requirement(district="Kampala", latitude=0.35, longitude=32.58), today=TODAY
    )
    assert scores.distance_km is not None and scores.distance_km < 12


def test_distance_km_is_symmetric_and_zero_for_same_point():
    a = (0.3476, 32.5825)
    b = (1.8500, 32.4833)
    assert matching.distance_km(a, a) == 0
    assert abs(matching.distance_km(a, b) - matching.distance_km(b, a)) < 1e-6
    assert 150 < matching.distance_km(a, b) < 200  # Kampala to Luwero


def test_recurring_requirement_gets_a_small_bonus():
    once = matching.score_pair(listing(), requirement(), today=TODAY)
    weekly = matching.score_pair(listing(), requirement(is_recurring_weekly=True), today=TODAY)
    assert weekly.components["quantity"] >= once.components["quantity"]
    assert any("recurs weekly" in e for e in weekly.explanations)
