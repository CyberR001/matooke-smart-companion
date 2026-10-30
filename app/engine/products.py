"""5.3 Surplus management and trending products: processing economics.

The proposal sets the rule for this module: compare expected product revenue
with raw-material, processing, packaging, transport, quality-control and
selling costs, and only claim profitability from measured trials. Two numbers
carry the whole argument:

    processing yield (%)  = output weight / fresh input weight * 100
    gross margin (UGX)    = selling revenue - direct costs

A catalog of *assumptions* is used until a `ProductTrial` exists for a
product; once a trial exists, its measured yield and costs take over and the
result is labelled `measured` instead of `assumed`.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

KNOWLEDGE = Path(__file__).parent / "knowledge" / "matooke_products.json"


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(KNOWLEDGE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def product_keys() -> tuple[str, ...]:
    return tuple(p["key"] for p in catalog()["products"])


def product_spec(key: str) -> dict:
    for p in catalog()["products"]:
        if p["key"] == key:
            return p
    raise KeyError(f"Unknown product key: {key}")


@dataclass
class CostBreakdown:
    raw_material: int = 0
    labour: int = 0
    energy: int = 0
    packaging: int = 0
    additives: int = 0
    cold_chain: int = 0
    transport: int = 0
    quality_control: int = 0

    @property
    def total(self) -> int:
        return sum(v for k, v in asdict(self).items() if k != "total")

    def items(self) -> list[tuple[str, int]]:
        return [(k, v) for k, v in asdict(self).items() if v]


@dataclass
class ProductEconomics:
    product_key: str
    product_name: str
    source: str  # "measured" | "assumed"
    fresh_kg: float
    output_kg: float
    yield_pct: float
    spoilage_pct: float
    selling_price_ugx_per_kg: int
    revenue_ugx: int
    costs: CostBreakdown
    margin_ugx: int = 0
    margin_pct: float = 0.0
    margin_per_fresh_kg_ugx: float = 0.0
    break_even_output_kg: float | None = None
    notes: list[str] = field(default_factory=list)
    shelf_life_days: int = 0
    complexity: int = 3
    demand_signal: float = 0.5
    demand_basis: str = ""
    risks: list[str] = field(default_factory=list)

    @property
    def is_profitable(self) -> bool:
        return self.margin_ugx > 0


def _trial_overrides(trial: dict | None) -> dict:
    if not trial:
        return {}
    fresh = float(trial.get("fresh_input_kg") or 0)
    out = float(trial.get("output_kg") or 0)
    o: dict = {}
    if fresh > 0 and out > 0:
        o["yield_pct"] = out / fresh * 100.0
    if trial.get("spoilage_pct") is not None:
        o["spoilage_pct"] = float(trial["spoilage_pct"])
    if trial.get("processing_hours") and fresh > 0:
        o["labour_hours_per_100kg_fresh"] = float(trial["processing_hours"]) / fresh * 100.0
    # Per-trial absolute costs become per-kg-output rates for the projection.
    if out > 0:
        for src, dst in (
            ("energy_ugx", "energy_ugx_per_kg_output"),
            ("packaging_ugx", "packaging_ugx_per_kg_output"),
            ("transport_ugx", "_transport_per_kg_output"),
        ):
            if trial.get(src):
                o[dst] = float(trial[src]) / out
        if trial.get("labour_ugx"):
            o["_labour_total"] = float(trial["labour_ugx"])
    if trial.get("selling_price_ugx_per_kg"):
        o["selling_price_ugx_per_kg"] = int(trial["selling_price_ugx_per_kg"])
    return o


def estimate_economics(
    product_key: str,
    *,
    fresh_kg: float | None = None,
    target_output_kg: float | None = None,
    trial: dict | None = None,
    fresh_price_ugx_per_kg: int | None = None,
    fixed_costs_ugx: int = 0,
    transport_ugx: int = 0,
    quality_control_ugx: int = 0,
) -> ProductEconomics:
    """Compute yield, costs and margin for one product.

    Provide either `fresh_kg` (what the farmer has) or `target_output_kg`
    (what a buyer/Hub notice wants) - the other is derived from yield.
    """
    spec = product_spec(product_key)
    basis = catalog()["cost_basis"]
    ov = _trial_overrides(trial)
    source = "measured" if ov else "assumed"

    yield_pct = float(ov.get("yield_pct", spec["yield_pct"]))
    yield_frac = max(yield_pct, 1.0) / 100.0
    spoilage = float(ov.get("spoilage_pct", 0.0)) / 100.0

    if fresh_kg is None and target_output_kg is None:
        raise ValueError("Provide fresh_kg or target_output_kg")
    if fresh_kg is None:
        fresh_kg = float(target_output_kg) / yield_frac
    fresh_kg = float(fresh_kg)
    output_kg = fresh_kg * yield_frac * (1.0 - spoilage)

    fresh_price = int(
        fresh_price_ugx_per_kg if fresh_price_ugx_per_kg is not None else basis["fresh_matooke_ugx_per_kg"]
    )
    labour_rate = int(basis["labour_ugx_per_hour"])
    hours_per_100 = float(ov.get("labour_hours_per_100kg_fresh", spec["labour_hours_per_100kg_fresh"]))
    labour_ugx = (
        int(ov["_labour_total"])
        if "_labour_total" in ov
        else int(fresh_kg / 100.0 * hours_per_100 * labour_rate)
    )

    costs = CostBreakdown(
        raw_material=int(fresh_kg * fresh_price),
        labour=labour_ugx,
        energy=int(
            output_kg * float(ov.get("energy_ugx_per_kg_output", spec.get("energy_ugx_per_kg_output", 0)))
        ),
        packaging=int(
            output_kg
            * float(
                ov.get(
                    "packaging_ugx_per_kg_output",
                    spec.get("packaging_ugx_per_kg_output", basis["packaging_ugx_per_kg_default"]),
                )
            )
        ),
        additives=int(output_kg * float(spec.get("additive_cost_ugx_per_kg_output", 0))),
        cold_chain=int(output_kg * float(spec.get("cold_chain_ugx_per_kg", 0))),
        transport=int(ov.get("_transport_per_kg_output", 0) * output_kg) + int(transport_ugx),
        quality_control=int(quality_control_ugx),
    )
    price = int(ov.get("selling_price_ugx_per_kg", spec["selling_price_ugx_per_kg"]))
    revenue = int(output_kg * price)
    margin = revenue - costs.total
    margin_pct = (margin / revenue * 100.0) if revenue > 0 else 0.0

    notes: list[str] = []
    if source == "assumed":
        notes.append(
            "Based on catalog assumptions, not a measured trial. Run a trial batch "
            "and record input/output weight, hours and costs before quoting this margin."
        )
    else:
        notes.append(f"Yield and unit costs taken from trial on {trial.get('trial_date', 'recorded date')}.")
    if spoilage:
        notes.append(f"{spoilage * 100:.0f} % spoilage/rework loss applied to output.")
    if spec.get("complexity", 3) >= 5:
        notes.append("Needs infrastructure (e.g. reliable cold chain) that is rarely available on-farm.")

    break_even = None
    if fixed_costs_ugx > 0:
        contribution_per_kg = (margin / output_kg) if output_kg > 0 else 0.0
        break_even = (fixed_costs_ugx / contribution_per_kg) if contribution_per_kg > 0 else math.inf

    return ProductEconomics(
        product_key=product_key,
        product_name=spec["name"],
        source=source,
        fresh_kg=round(fresh_kg, 1),
        output_kg=round(output_kg, 2),
        yield_pct=round(yield_pct, 1),
        spoilage_pct=round(spoilage * 100, 1),
        selling_price_ugx_per_kg=price,
        revenue_ugx=revenue,
        costs=costs,
        margin_ugx=margin,
        margin_pct=round(margin_pct, 1),
        margin_per_fresh_kg_ugx=round(margin / fresh_kg, 1) if fresh_kg else 0.0,
        break_even_output_kg=None if break_even in (None, math.inf) else round(break_even, 1),
        notes=notes,
        shelf_life_days=int(spec.get("shelf_life_days", 0)),
        complexity=int(spec.get("complexity", 3)),
        demand_signal=float(spec.get("demand_signal", 0.5)),
        demand_basis=spec.get("demand_basis", ""),
        risks=list(spec.get("risks", [])),
    )


@dataclass
class Recommendation:
    product_key: str
    product_name: str
    score: float
    verdict: str
    reasons: list[str]
    contributions: dict[str, float]
    economics: ProductEconomics
    hub_is_buying: bool


WEIGHTS = {
    "demand": 0.30,
    "margin": 0.30,
    "feasibility": 0.15,
    "shelf_life": 0.10,
    "hub_pull": 0.15,
}


def rank_products(
    *,
    fresh_kg: float,
    trials: dict[str, dict] | None = None,
    hub_buying_keys: set[str] | None = None,
    available_services: set[str] | None = None,
    min_margin_pct: float = 15.0,
    fresh_price_ugx_per_kg: int | None = None,
) -> list[Recommendation]:
    """Explainable ranking: every component of the score is reported.

    `available_services` may include "dryer", "mill", "fryer", "cold_chain",
    "partner_processor" and shifts what is realistic for this farmer.
    """
    trials = trials or {}
    hub_buying_keys = hub_buying_keys or set()
    services = available_services or set()

    recs: list[Recommendation] = []
    for spec in catalog()["products"]:
        key = spec["key"]
        econ = estimate_economics(
            key,
            fresh_kg=fresh_kg,
            trial=trials.get(key),
            fresh_price_ugx_per_kg=fresh_price_ugx_per_kg,
        )
        demand = max(0.0, min(float(spec.get("demand_signal", 0.5)), 1.0))
        margin_score = max(0.0, min(econ.margin_pct / 40.0, 1.0))
        needs = set()
        equipment_blob = " ".join(spec.get("equipment", [])).lower()
        if "dryer" in equipment_blob or "drying" in equipment_blob:
            needs.add("dryer")
        if "mill" in equipment_blob:
            needs.add("mill")
        if "fryer" in equipment_blob:
            needs.add("fryer")
        if "freezer" in equipment_blob or "cold room" in equipment_blob:
            needs.add("cold_chain")
        missing = needs - services - {"partner_processor"}
        feasibility = 1.0 - 0.25 * len(missing) - 0.05 * max(0, int(spec.get("complexity", 3)) - 2)
        feasibility = max(0.0, min(feasibility, 1.0))
        shelf = min(econ.shelf_life_days / 270.0, 1.0)
        hub_pull = 1.0 if key in hub_buying_keys else 0.35

        contributions = {
            "demand": round(WEIGHTS["demand"] * demand, 3),
            "margin": round(WEIGHTS["margin"] * margin_score, 3),
            "feasibility": round(WEIGHTS["feasibility"] * feasibility, 3),
            "shelf_life": round(WEIGHTS["shelf_life"] * shelf, 3),
            "hub_pull": round(WEIGHTS["hub_pull"] * hub_pull, 3),
        }
        score = round(sum(contributions.values()), 3)

        reasons: list[str] = []
        reasons.append(
            f"Demand signal {demand * 100:.0f}/100 ({spec.get('demand_basis', 'no basis recorded')})"
        )
        reasons.append(
            f"Indicative margin {econ.margin_pct:.0f} % ({econ.margin_ugx:,} UGX on {econ.output_kg:.1f} kg output from {econ.fresh_kg:.0f} kg fresh) - {econ.source}"
        )
        if missing:
            reasons.append("Missing: " + ", ".join(sorted(missing)))
        else:
            reasons.append("Processing steps look achievable with what is available")
        reasons.append(
            f"Shelf life about {econ.shelf_life_days} days"
            + (" and the Hub is buying this now" if key in hub_buying_keys else "")
        )
        if econ.margin_pct < min_margin_pct:
            verdict = "not yet attractive"
            reasons.append(
                f"Margin is below the {min_margin_pct:.0f} % threshold we use to call value addition worthwhile."
            )
        elif score >= 0.6:
            verdict = "worth a trial batch"
        else:
            verdict = "possible, needs checks"

        recs.append(
            Recommendation(
                product_key=key,
                product_name=spec["name"],
                score=score,
                verdict=verdict,
                reasons=reasons,
                contributions=contributions,
                economics=econ,
                hub_is_buying=key in hub_buying_keys,
            )
        )
    return sorted(recs, key=lambda r: (-r.score, r.product_name))


def fresh_kg_needed_for_income(
    product_key: str,
    target_income_ugx: int,
    *,
    fresh_price_ugx_per_kg: int | None = None,
    trial: dict | None = None,
) -> dict:
    """How much fresh matooke must be processed to earn a target contribution.

    Used when a farmer's real question is 'I need UGX 400,000 this month'.
    Solved by linear scaling of margin per fresh kg, then verified directly.
    """
    per_kg = estimate_economics(
        product_key, fresh_kg=100.0, trial=trial, fresh_price_ugx_per_kg=fresh_price_ugx_per_kg
    )
    margin_per_kg = per_kg.margin_ugx / 100.0
    if margin_per_kg <= 0:
        return {
            "possible": False,
            "reason": (
                f"{per_kg.product_name} as modelled loses money per kg of fresh matooke "
                "processed. Fix the cost or price basis before adding volume."
            ),
            "margin_per_fresh_kg_ugx": round(margin_per_kg, 1),
        }
    needed_kg = target_income_ugx / margin_per_kg
    check = estimate_economics(
        product_key, fresh_kg=needed_kg, trial=trial, fresh_price_ugx_per_kg=fresh_price_ugx_per_kg
    )
    return {
        "possible": True,
        "fresh_kg_needed": round(needed_kg, 1),
        "bunches_approx": round(needed_kg / 30.0, 1),
        "expected_output_kg": check.output_kg,
        "expected_margin_ugx": check.margin_ugx,
        "margin_per_fresh_kg_ugx": round(margin_per_kg, 1),
        "assumption_note": (
            "Uses per-kg margins that do not scale perfectly (drying capacity, labour and "
            "transport have fixed parts). Treat as an order-of-magnitude figure."
        ),
    }


def summary_dict(rec: Recommendation) -> dict:
    d = asdict(rec)
    d.pop("economics", None)
    return d
