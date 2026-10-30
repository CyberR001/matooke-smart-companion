"""5.5 Buyer matching: transparent, explainable, greedy.

Section 7 of the proposal allows a greedy matcher for the prototype. The score
below is reported with its components so a farmer or buyer can see *why* a
match was suggested - important for trust, and it makes the weights testable
in the field.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date

# Approximate district centroids (degrees). Rough on purpose: enough for
# "is this reachable today" ordering, not for navigation.
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "kampala": (0.3476, 32.5825),
    "wakiso": (0.4257, 32.4689),
    "mukono": (0.3514, 32.7564),
    "luwero": (1.8500, 32.4833),
    "nakaseke": (1.4667, 32.0833),
    "mityana": (0.4080, 32.0340),
    "kayunga": (0.7561, 32.8964),
    "masaka": (-0.3397, 31.7387),
    "lwengo": (-0.4200, 31.3600),
    "rakai": (-0.7210, 31.4000),
    "mubende": (0.5611, 31.4631),
    "hoima": (1.4330, 31.3570),
    "kiryandongo": (1.9000, 32.0830),
    "kyegegwa": (-0.4667, 31.0506),
    "kamwenge": (0.1940, 30.4580),
    "kasese": (0.1800, 30.0900),
    "fort portal": (0.6667, 30.2836),
    "kabarole": (0.6600, 30.3000),
    "sheema": (-0.6000, 30.1300),
    "bushenyi": (-0.6040, 30.2050),
    "rukungiri": (-0.8250, 29.9280),
    "rubirizi": (-0.4830, 30.1500),
    "kabale": (-1.2530, 29.9850),
    "kanungu": (-1.0830, 29.7830),
    "iganga": (0.7930, 33.4660),
    "jinja": (0.4247, 33.2040),
    "buyende": (0.2000, 33.8000),
    "pallisa": (1.1440, 33.7200),
    "mbale": (1.0850, 34.1750),
    "butaleja": (1.1100, 34.2200),
    "soroti": (1.7070, 33.6040),
    "kumi": (1.4000, 33.9200),
    "lira": (2.2460, 32.9000),
    "apac": (1.9890, 32.5240),
    "nakasongola": (1.2040, 32.1300),
    "luweero": (1.8500, 32.4833),
    "gulu": (2.7750, 32.2970),
    "amuru": (2.5300, 33.0000),
    "arua": (3.0200, 30.9170),
    "yumbe": (3.4700, 31.2500),
    "masindi": (0.3500, 31.7330),
    "buikwe": (0.7000, 32.4500),
    "lyantonde": (-0.7200, 31.1400),
    "semuliki": (1.7000, 33.5500),
    "nalufenya": (1.5500, 33.2000),
}

GRADES = {"ungraded": 0, "low": 1, "medium": 2, "high": 3, "premium": 4}

WEIGHTS = {
    "proximity": 0.30,
    "quantity": 0.25,
    "timing": 0.20,
    "price": 0.15,
    "quality": 0.10,
}

# Fresh matooke does not sit around: a lot harvested far before it is needed is
# as useless as one that arrives late.
FRESH_WINDOW_DAYS = 21


def _key(district: str | None) -> str:
    return (district or "").strip().lower()


def centroid(district: str | None, lat: float | None = None, lng: float | None = None):
    if lat is not None and lng is not None:
        return float(lat), float(lng)
    return DISTRICT_CENTROIDS.get(_key(district))  # type: ignore[return-value]


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine distance in km."""
    (lat1, lon1), (lat2, lon2) = a, b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


@dataclass
class MatchScore:
    score: float
    components: dict[str, float]
    explanations: list[str]
    distance_km: float | None
    quantity_bunches: int
    suggested_price_ugx_per_bunch: int
    price_gap_ugx: int
    timing_note: str


@dataclass
class Candidate:
    listing_id: int
    requirement_id: int
    farmer_name: str
    buyer_name: str
    product: str
    district_pair: str
    score: MatchScore
    status_note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score"] = asdict(self.score)
        return d


def score_pair(
    listing: dict,
    requirement: dict,
    *,
    today: date | None = None,
) -> MatchScore:
    """Score one (listing, requirement) pair. Dicts keep this DB-agnostic."""
    today = today or date.today()
    exp: list[str] = []

    # proximity -----------------------------------------------------------
    la = centroid(listing.get("district"), listing.get("latitude"), listing.get("longitude"))
    lb = centroid(requirement.get("district"), requirement.get("latitude"), requirement.get("longitude"))
    dist = None
    if la and lb:
        dist = round(distance_km(la, lb), 1)
        prox = math.exp(-dist / 90.0)
        exp.append(f"{dist:.0f} km apart (score {prox:.2f})")
    elif _key(listing.get("district")) == _key(requirement.get("district")):
        prox = 1.0
        exp.append("same district, no coordinates recorded")
    else:
        prox = 0.45
        exp.append(
            f"{listing.get('district') or 'unknown'} to {requirement.get('district') or 'unknown'}: "
            "no distance data, treated as medium"
        )

    # quantity --------------------------------------------------------------
    avail = max(int(listing.get("quantity_bunches", 0)) - int(listing.get("committed_bunches", 0)), 0)
    need = max(int(requirement.get("quantity_bunches", 0)), 1)
    ratio = min(avail / need, 1.0)
    if avail >= need:
        qscore = 1.0
        qty = need
        exp.append(f"listing covers the full {need} bunches")
    else:
        qscore = 0.35 + 0.5 * ratio
        qty = avail
        exp.append(f"listing covers only {avail} of {need} bunches")

    # timing ----------------------------------------------------------------
    harvest = listing.get("expected_harvest_date")
    needed = requirement.get("needed_by")
    timing = 0.5
    timing_note = "no delivery date on the requirement"
    if harvest and needed:
        lag = (needed - harvest).days  # >0 means harvested before it is needed
        if lag < -3:
            timing = max(0.1, math.exp(-abs(lag) / 30.0))
            timing_note = f"harvest about {abs(lag)} days after the buyer needs it"
        elif lag <= FRESH_WINDOW_DAYS:
            timing = 1.0
            timing_note = f"harvest {lag} day(s) before the needed date - fresh window met"
        else:
            timing = max(0.25, math.exp(-(lag - FRESH_WINDOW_DAYS) / 45.0))
            timing_note = (
                f"harvest is {lag} days before it is needed; fresh matooke will not keep, "
                "so this only works as a pre-order you deliver on their date"
            )
        exp.append(timing_note)

    # price -----------------------------------------------------------------
    asking = int(listing.get("asking_price_ugx_per_bunch", 0) or 0)
    ceiling = int(requirement.get("max_price_ugx_per_bunch", 0) or 0)
    gap = 0
    if asking and ceiling:
        if asking <= ceiling:
            price = 1.0
            suggested = asking
            exp.append(f"asking {asking:,} UGX is within the buyer's ceiling of {ceiling:,} UGX")
        else:
            over = (asking - ceiling) / ceiling
            price = max(0.0, math.exp(-over / 0.15))
            suggested = ceiling
            exp.append(f"asking is {asking - ceiling:,} UGX above the buyer's ceiling")
        gap = asking - ceiling
    else:
        price = 0.6
        suggested = asking or ceiling
        exp.append("one side has not stated a price")

    # quality ---------------------------------------------------------------
    lg = GRADES.get(_key(listing.get("grade")), 2)
    rg = GRADES.get(_key(requirement.get("min_grade")), 2)
    if lg >= rg:
        quality = 1.0
        exp.append("grade meets the buyer's minimum")
    else:
        quality = 0.4
        exp.append("grade is below the buyer's stated minimum - agree or reject explicitly")

    # recurring orders get a small nudge: they are worth more to the Hub -----
    if requirement.get("is_recurring_weekly"):
        qscore = min(1.0, qscore + 0.05)
        exp.append("requirement recurs weekly, which favours a standing supplier")

    components = {
        "proximity": prox,
        "quantity": qscore,
        "timing": timing,
        "price": price,
        "quality": quality,
    }
    score = round(sum(WEIGHTS[k] * v for k, v in components.items()), 3)
    return MatchScore(
        score=score,
        components={k: round(v, 3) for k, v in components.items()},
        explanations=exp,
        distance_km=dist,
        quantity_bunches=qty,
        suggested_price_ugx_per_bunch=int(suggested or 0),
        price_gap_ugx=gap,
        timing_note=timing_note,
    )


def match_all(
    listings: list[dict],
    requirements: list[dict],
    *,
    min_score: float = 0.35,
    today: date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Greedy one-pass matcher with capacity consumption.

    Returns (suggestions, leftovers). A listing can serve several requirements
    until its uncommitted quantity runs out, which is what a real farmer does.
    """
    remaining = {
        lst["id"]: max(int(lst.get("quantity_bunches", 0)) - int(lst.get("committed_bunches", 0)), 0)
        for lst in listings
    }
    open_need = {r["id"]: int(r.get("quantity_bunches", 0)) for r in requirements}

    pairs: list[tuple[float, dict, dict, MatchScore]] = []
    for lst in listings:
        for req in requirements:
            if remaining.get(lst["id"], 0) <= 0 or open_need.get(req["id"], 0) <= 0:
                continue
            view = dict(lst)
            view["quantity_bunches"] = remaining[lst["id"]]
            scored = score_pair(view, req, today=today)
            if scored.score >= min_score:
                pairs.append((scored.score, lst, req, scored))

    # Deterministic: score desc, then ids, so CI and demo runs agree.
    pairs.sort(key=lambda t: (-t[0], t[1]["id"], t[2]["id"]))

    suggestions: list[dict] = []
    for score, lst, req, ms in pairs:
        alloc = min(remaining[lst["id"]], open_need[req["id"]], ms.quantity_bunches)
        if alloc <= 0:
            continue
        remaining[lst["id"]] -= alloc
        open_need[req["id"]] -= alloc
        suggestions.append(
            {
                "listing_id": lst["id"],
                "requirement_id": req["id"],
                "farmer_name": lst.get("seller_name", "farmer"),
                "buyer_name": req.get("organisation") or req.get("buyer_name", "buyer"),
                "district_pair": f"{lst.get('district')} -> {req.get('district')}",
                "quantity_bunches": alloc,
                "suggested_price_ugx_per_bunch": ms.suggested_price_ugx_per_bunch,
                "order_value_ugx": alloc * ms.suggested_price_ugx_per_bunch,
                "score": score,
                "components": ms.components,
                "explanations": ms.explanations,
                "distance_km": ms.distance_km,
                "timing_note": ms.timing_note,
            }
        )

    leftovers = [
        {"kind": "listing", "id": k, "unmatched_bunches": v} for k, v in sorted(remaining.items()) if v > 0
    ] + [{"kind": "requirement", "id": k, "unmet_bunches": v} for k, v in sorted(open_need.items()) if v > 0]
    return suggestions, leftovers


def best_counterpart_price(listing: dict, requirement: dict) -> tuple[int, int]:
    """Return (negotiation floor, ceiling) for a suggested pair."""
    asking = int(listing.get("asking_price_ugx_per_bunch", 0) or 0)
    ceiling = int(requirement.get("max_price_ugx_per_bunch", 0) or 0)
    if asking and ceiling:
        return min(asking, ceiling), max(asking, ceiling)
    return asking or ceiling, ceiling or asking
