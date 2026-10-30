"""Opportunity centre: verification and expiry must be enforced, not decorative."""

from __future__ import annotations

from datetime import date, timedelta

from app.engine import opportunities as opp

TODAY = date(2026, 10, 30)


def item(**kw):
    base = {
        "id": 1,
        "title": "Free suckers",
        "status": "published",
        "is_verified": True,
        "verified_on": TODAY - timedelta(days=4),
        "opens_on": TODAY - timedelta(days=10),
        "deadline": TODAY + timedelta(days=30),
        "districts": ["Mukono"],
        "kind": "input_support",
        "source_name": "District Production Department",
    }
    base.update(kw)
    return base


def test_past_deadline_becomes_expired_and_is_not_current():
    eff = opp.effective_status(
        status="published",
        deadline=TODAY - timedelta(days=1),
        verified_on=TODAY,
        is_verified=True,
        today=TODAY,
    )
    assert eff["status"] == "expired"
    assert eff["may_show_as_current"] is False


def test_unverified_notice_is_labelled_and_not_shown_as_current():
    eff = opp.effective_status(
        status="published", is_verified=False, today=TODAY, deadline=TODAY + timedelta(days=9)
    )
    assert eff["status"] == "unverified"
    assert eff["may_show_as_current"] is False
    assert any("unconfirmed" in f or "checked" in f for f in eff["flags"])


def test_stale_verification_forces_a_recheck():
    eff = opp.effective_status(
        status="published",
        is_verified=True,
        verified_on=TODAY - timedelta(days=400),
        deadline=TODAY + timedelta(days=40),
        today=TODAY,
    )
    assert eff["status"] == "needs_recheck"


def test_closing_soon_is_flagged():
    eff = opp.effective_status(
        status="published",
        is_verified=True,
        verified_on=TODAY,
        deadline=TODAY + timedelta(days=6),
        today=TODAY,
    )
    assert eff["status"] == "closing_soon"
    assert any("apply early" in f for f in eff["flags"])


def test_drafts_are_never_displayable():
    eff = opp.effective_status(status="draft", today=TODAY)
    assert eff["displayable"] is False


def test_expired_is_removed_and_unverified_is_kept_but_never_marked_current():
    """An unconfirmed notice stays visible so farmers can be warned about it,
    but it must never be labelled as a current opportunity."""
    items = [
        item(id=1),
        item(id=2, deadline=TODAY - timedelta(days=2)),
        item(id=3, is_verified=False, verified_on=None),
    ]
    current = opp.filter_for(items, today=TODAY)
    assert {i["id"] for i in current} == {1, 3}
    assert {i["id"] for i in current if i["effective"]["may_show_as_current"]} == {1}
    unverified = next(i for i in current if i["id"] == 3)
    assert unverified["effective"]["status"] == "unverified"
    assert any("unconfirmed" in f for f in unverified["effective"]["flags"])

    everything = opp.filter_for(items, today=TODAY, only_current=False)
    assert {i["id"] for i in everything} == {1, 2, 3}
    assert all("effective" in i for i in everything)
    expired = next(i for i in everything if i["id"] == 2)
    assert any("Deadline passed" in f for f in expired["effective"]["flags"])


def test_district_filter_is_case_insensitive():
    items = [item(id=1, districts=["Mukono"]), item(id=2, districts=["Gulu"])]
    out = opp.filter_for(items, district="mukono", today=TODAY)
    assert [i["id"] for i in out] == [1]


def test_nationwide_notice_passes_any_district_filter():
    items = [item(id=1, districts=None)]
    assert len(opp.filter_for(items, district="Ntungamo", today=TODAY)) == 1


def test_source_line_always_shows_source_and_check_date():
    line = opp.source_line(item(id=1))
    assert "District Production Department" in line
    assert "checked" in line
    orphan = opp.source_line({"source_name": "WhatsApp", "verified_on": None})
    assert "check date not recorded" in orphan


def test_needs_recheck_helper():
    assert opp.needs_recheck(None) is True
    assert opp.needs_recheck(TODAY, today=TODAY) is False
    assert opp.needs_recheck(TODAY - timedelta(days=200), today=TODAY) is True
