"""5.6 Government opportunities: verification and expiry rules.

Section 13 requires that announcements show source, date checked and
eligibility, and that expired or unverified items are never presented as
current. That is enforced here: `effective_status` can downgrade what a
`status` column says, and the UI is given a reason it can display.
"""

from __future__ import annotations

from datetime import date, timedelta

EXPIRING_SOON_DAYS = 21

LABELS = {
    "input_support": "Inputs / planting material",
    "training": "Training and extension",
    "grant": "Grant or subsidy",
    "programme": "Government programme",
    "market_support": "Market and storage support",
    "standards": "Standards and certification",
}


def effective_status(
    *,
    status: str,
    opens_on: date | None = None,
    deadline: date | None = None,
    verified_on: date | None = None,
    is_verified: bool = False,
    today: date | None = None,
    staleness_days: int = 120,
) -> dict:
    """Derive the truth from the dates rather than trusting a stored label."""
    today = today or date.today()
    flags: list[str] = []

    if status == "draft":
        return {"status": "internal_draft", "displayable": False, "flags": ["Not published."]}
    if status == "retired":
        return {"status": "closed", "displayable": True, "flags": ["Closed by MatookeSmart."]}

    if opens_on and today < opens_on:
        flags.append(f"Opens on {opens_on:%d %b %Y}.")
        derived = "opening_soon" if (opens_on - today).days <= EXPIRING_SOON_DAYS else "not_open"
    elif deadline and today > deadline:
        flags.append(f"Deadline passed on {deadline:%d %b %Y}.")
        derived = "expired"
    elif deadline and (deadline - today).days <= EXPIRING_SOON_DAYS:
        flags.append(f"Closing in {(deadline - today).days} day(s) - apply early.")
        derived = "closing_soon"
    else:
        derived = "open"

    if not is_verified:
        flags.append("Not yet checked by a MatookeSmart officer, so treat every detail as unconfirmed.")
        if derived in {"open", "closing_soon"}:
            derived = "unverified"
    elif verified_on and (today - verified_on).days > staleness_days:
        flags.append(
            f"Last checked {verified_on:%d %b %Y}, more than {staleness_days} days ago. "
            "Confirm with the source before relying on it."
        )
        if derived == "open":
            derived = "needs_recheck"

    return {
        "status": derived,
        "displayable": derived != "internal_draft",
        "flags": flags,
        "may_show_as_current": derived in {"open", "closing_soon"},
    }


def filter_for(
    items: list[dict],
    *,
    district: str | None = None,
    kind: str | None = None,
    only_current: bool = True,
    today: date | None = None,
) -> list[dict]:
    """District/type filtering plus the 'never show stale as current' rule."""
    out: list[dict] = []
    for raw in items:
        item = dict(raw)
        eff = effective_status(
            status=item.get("status", "open"),
            opens_on=item.get("opens_on"),
            deadline=item.get("deadline"),
            verified_on=item.get("verified_on"),
            is_verified=bool(item.get("is_verified")),
            today=today,
        )
        item["effective"] = eff
        if not eff["displayable"]:
            continue
        if only_current and eff["status"] in {"expired", "not_open"}:
            continue
        districts = item.get("districts")
        if district and districts:
            wanted = district.strip().lower()
            if not any(wanted in str(d).strip().lower() for d in districts):
                continue
        if kind and item.get("kind") != kind:
            continue
        item["kind_label"] = LABELS.get(item.get("kind", ""), "Agricultural support")
        out.append(item)
    out.sort(key=lambda i: (i.get("deadline") or date.max, -(i.get("priority") or 0)))
    return out


def needs_recheck(verified_on: date | None, today: date | None = None, days: int = 120) -> bool:
    if not verified_on:
        return True
    return (today or date.today()) - verified_on > timedelta(days=days)


def source_line(item: dict) -> str:
    """The attribution string the UI must render next to every notice."""
    parts = [item.get("source_name") or "source not recorded"]
    if item.get("verified_on"):
        parts.append(f"checked {item['verified_on']:%d %b %Y}")
    else:
        parts.append("check date not recorded")
    if item.get("verified_by"):
        parts.append(f"by {item['verified_by']}")
    if item.get("source_url"):
        parts.append(str(item["source_url"]))
    return " - ".join(parts)
