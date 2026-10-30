"""Glue between the database and the engines in app/engine.

Keeping this in one file means the routers stay thin and the engines stay
pure functions (easy to unit test without a database).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .engine import diseases, earlyorders, entitlements, matching, opportunities, products, sell_advice
from .engine.prices import PriceForecast, PricePoint, forecast_prices

DEFAULT_HORIZON_DAYS = 60
HISTORY_DAYS = 900


# --------------------------------------------------------------------------
# 5.2 market data
# --------------------------------------------------------------------------


def price_points(db: Session, market_id: int, *, days: int = HISTORY_DAYS) -> list[PricePoint]:
    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.market_id == market_id, models.PriceRecord.observed_on >= since)
        .order_by(models.PriceRecord.observed_on)
    ).all()
    return [PricePoint(day=r.observed_on, price_ugx=r.price_ugx, verified=r.verified) for r in rows]


def forecast_for_market(
    db: Session, market_id: int, *, horizon_days: int = DEFAULT_HORIZON_DAYS
) -> PriceForecast:
    market = db.get(models.Market, market_id)
    if not market:
        raise KeyError(f"No market {market_id}")
    fc = forecast_prices(
        price_points(db, market_id),
        market_name=market.name,
        horizon_days=horizon_days,
    )
    fc.unit = market.unit
    fc.data_is_synthetic = all(
        p.is_synthetic
        for p in db.scalars(select(models.PriceRecord).where(models.PriceRecord.market_id == market_id))
    )
    return fc


def market_for_district(db: Session, district: str | None) -> models.Market | None:
    if district:
        m = db.scalars(
            select(models.Market).where(
                func.lower(models.Market.district) == district.strip().lower(),
                models.Market.is_active.is_(True),
            )
        ).first()
        if m:
            return m
    return db.scalars(
        select(models.Market).where(models.Market.is_active.is_(True)).order_by(models.Market.id)
    ).first()


def latest_price(db: Session, market_id: int) -> models.PriceRecord | None:
    return db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.market_id == market_id)
        .order_by(models.PriceRecord.observed_on.desc())
    ).first()


def best_requirement_price(
    db: Session, district: str | None, *, product: str = "fresh_matooke"
) -> int | None:
    """Median ceiling among open requirements - what buyers really offer nearby."""
    rows = db.scalars(
        select(models.BuyerRequirement.max_price_ugx_per_bunch).where(
            models.BuyerRequirement.status == "open", models.BuyerRequirement.product == product
        )
    ).all()
    if district:
        near = db.scalars(
            select(models.BuyerRequirement.max_price_ugx_per_bunch).where(
                models.BuyerRequirement.status == "open",
                models.BuyerRequirement.product == product,
                func.lower(models.BuyerRequirement.district) == district.strip().lower(),
            )
        ).all()
        if near:
            rows = near
    if not rows:
        return None
    vals = sorted(rows)
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else int((vals[mid - 1] + vals[mid]) / 2)


# --------------------------------------------------------------------------
# 5.3 Hub and value addition
# --------------------------------------------------------------------------


def live_hub_notices(db: Session) -> list[dict]:
    notices = db.scalars(select(models.HubBuyingNotice)).all()
    return [
        {
            "id": n.id,
            "title": n.title,
            "accepts": n.accepts,
            "accepts_form": n.accepts_form,
            "quality_spec": n.quality_spec,
            "quantity_kg": n.quantity_kg,
            "price_basis": n.price_basis,
            "price_ugx_per_unit": n.price_ugx_per_unit,
            "district": n.district,
            "pickup_point": n.pickup_point,
            "closes_on": n.closes_on,
            "purchase_limit_kg": n.purchase_limit_kg,
        }
        for n in notices
        if n.is_live
    ]


def hub_buying_keys(db: Session) -> set[str]:
    return {n["accepts"] for n in live_hub_notices(db) if n.get("accepts")}


def measured_trials(db: Session) -> dict[str, dict]:
    """Latest trial per product, as the engine expects it."""
    out: dict[str, dict] = {}
    for t in db.scalars(select(models.ProductTrial).order_by(models.ProductTrial.trial_date.desc())):
        out.setdefault(
            t.product_key,
            {
                "trial_date": t.trial_date,
                "fresh_input_kg": t.fresh_input_kg,
                "output_kg": t.output_kg,
                "processing_hours": t.processing_hours,
                "labour_ugx": t.labour_ugx,
                "energy_ugx": t.energy_ugx,
                "packaging_ugx": t.packaging_ugx,
                "transport_ugx": t.transport_ugx,
                "spoilage_pct": t.spoilage_pct,
                "selling_price_ugx_per_kg": t.selling_price_ugx_per_kg,
                "fresh_price_ugx_per_kg": t.fresh_price_ugx_per_kg,
            },
        )
    return out


def product_recommendations(
    db: Session,
    *,
    fresh_kg: float,
    services: set[str] | None = None,
    min_margin_pct: float | None = None,
) -> list[dict]:
    recs = products.rank_products(
        fresh_kg=fresh_kg,
        trials=measured_trials(db),
        hub_buying_keys=hub_buying_keys(db),
        available_services=services,
        min_margin_pct=min_margin_pct if min_margin_pct is not None else settings.min_attractive_margin_pct,
    )
    return [_rec_dict(r) for r in recs]


def _rec_dict(r: products.Recommendation) -> dict:
    e = r.economics
    return {
        "product_key": r.product_key,
        "product_name": r.product_name,
        "score": r.score,
        "verdict": r.verdict,
        "reasons": r.reasons,
        "contributions": r.contributions,
        "hub_is_buying": r.hub_is_buying,
        "source": e.source,
        "fresh_kg": e.fresh_kg,
        "output_kg": e.output_kg,
        "yield_pct": e.yield_pct,
        "spoilage_pct": e.spoilage_pct,
        "selling_price_ugx_per_kg": e.selling_price_ugx_per_kg,
        "revenue_ugx": e.revenue_ugx,
        "costs": {k: v for k, v in e.costs.items() if v},
        "cost_total_ugx": e.costs.total,
        "margin_ugx": e.margin_ugx,
        "margin_pct": e.margin_pct,
        "margin_per_fresh_kg_ugx": e.margin_per_fresh_kg_ugx,
        "shelf_life_days": e.shelf_life_days,
        "complexity": e.complexity,
        "risks": e.risks,
        "notes": e.notes,
        "spec": products.product_spec(r.product_key),
    }


# --------------------------------------------------------------------------
# 5.1 farm doctor
# --------------------------------------------------------------------------


def doctor_assess(answers: dict[str, str], *, image_provided: bool = False) -> dict:
    a = diseases.assess(answers, image_provided=image_provided)
    d = diseases.to_dict(a)
    d["headline"] = diseases.safe_headline(a)
    if d.get("advice"):
        d["advice"]["free_access"] = True
        d["advice"]["references_note"] = (
            "Guidance is for orientation. Confirm with a qualified officer before buying or applying anything."
        )
        d["advice"]["next_question"] = d.get("next_question")
    return d


# --------------------------------------------------------------------------
# 5.2 + 5.3 + 5.4 combined advice for one farm
# --------------------------------------------------------------------------


def advice_for_farm(
    db: Session,
    farm: models.Farm,
    *,
    urgent_need_ugx: int = 0,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    quantity_bunches: int | None = None,
    harvest_date: date | None = None,
) -> dict:
    market = market_for_district(db, farm.district)
    listing = db.scalars(
        select(models.HarvestListing)
        .where(models.HarvestListing.farm_id == farm.id, models.HarvestListing.status == "open")
        .order_by(models.HarvestListing.id.desc())
    ).first()
    qty = int(
        quantity_bunches or (listing.quantity_bunches if listing else 0) or (farm.matooke_stands or 0) // 2
    )
    harvest = (
        harvest_date
        or (listing.expected_harvest_date if listing else None)
        or farm.expected_harvest_date
        or (date.today() + timedelta(days=21))
    )
    asking = listing.asking_price_ugx_per_bunch if listing else None

    fc = forecast_for_market(db, market.id, horizon_days=horizon_days)
    notices = live_hub_notices(db)
    hub_note = None
    if notices:
        n = notices[0]
        hub_note = (
            f"MatookeSmart Hub is currently buying: {n['title']} - {n['accepts_form']} up to "
            f"{n['quantity_kg']:,} kg at {n['price_ugx_per_unit']:,} {n['price_basis']} in {n['district']}"
            + (f", closing {n['closes_on']:%d %b}" if n.get("closes_on") else "")
            + ". Quality: "
            + n["quality_spec"]
        )
    advice = sell_advice.advise(
        fc,
        harvest_date=harvest,
        quantity_bunches=max(qty, 1),
        urgent_need_ugx=urgent_need_ugx,
        asking_price_ugx_per_bunch=asking,
        open_requirement_price_ugx=best_requirement_price(db, farm.district),
        hub_buying_note=hub_note,
    )
    fresh_kg = max(qty, 1) * sell_advice.DEFAULT_KG_PER_BUNCH
    recs = product_recommendations(db, fresh_kg=fresh_kg)
    return {
        "farm": farm,
        "market": market,
        "listing": listing,
        "forecast": fc,
        "advice": advice,
        "hub_note": hub_note,
        "fresh_kg_assumed": round(fresh_kg),
        "kg_per_bunch": sell_advice.DEFAULT_KG_PER_BUNCH,
        "recommendations": recs,
    }


# --------------------------------------------------------------------------
# 5.5 marketplace matching
# --------------------------------------------------------------------------


def _listing_dict(row: models.HarvestListing, db: Session) -> dict:
    farm = db.get(models.Farm, row.farm_id) if row.farm_id else None
    return {
        "id": row.id,
        "seller_name": row.seller.full_name if row.seller else "farmer",
        "district": row.district,
        "latitude": farm.latitude if farm else None,
        "longitude": farm.longitude if farm else None,
        "quantity_bunches": row.quantity_bunches,
        "committed_bunches": row.committed_bunches,
        "expected_harvest_date": row.expected_harvest_date,
        "asking_price_ugx_per_bunch": row.asking_price_ugx_per_bunch,
        "grade": row.grade,
        "quantity_confidence": row.quantity_confidence,
        "notes": row.notes,
    }


def match_suggestions(db: Session, *, min_score: float = 0.35, persist: bool = False) -> list[dict]:
    listings = db.scalars(select(models.HarvestListing).where(models.HarvestListing.status == "open")).all()
    requirements = db.scalars(
        select(models.BuyerRequirement).where(models.BuyerRequirement.status == "open")
    ).all()
    if not listings or not requirements:
        return []
    suggestions, _leftovers = matching.match_all(
        [_listing_dict(lst, db) for lst in listings],
        [
            {
                "id": r.id,
                "organisation": r.organisation or (r.buyer.full_name if r.buyer else "buyer"),
                "buyer_name": r.buyer.full_name if r.buyer else "buyer",
                "district": r.district,
                "quantity_bunches": r.quantity_bunches,
                "needed_by": r.needed_by,
                "is_recurring_weekly": r.is_recurring_weekly,
                "min_grade": r.min_grade,
                "max_price_ugx_per_bunch": r.max_price_ugx_per_bunch,
                "willing_deposit_pct": r.willing_deposit_pct,
                "product": r.product,
            }
            for r in requirements
        ],
        min_score=min_score,
    )
    if persist:
        for s in suggestions:
            db.add(
                models.MatchRun(
                    listing_id=s["listing_id"],
                    requirement_id=s["requirement_id"],
                    score=s["score"],
                    breakdown={k: v for k, v in s.items() if k not in {"explanations"}},
                )
            )
        db.commit()
    for s in suggestions:
        s["explanations"] = s.get("explanations", [])
    return suggestions


def unmatched_report(db: Session) -> dict:
    listings = db.scalars(select(models.HarvestListing).where(models.HarvestListing.status == "open")).all()
    reqs = db.scalars(select(models.BuyerRequirement).where(models.BuyerRequirement.status == "open")).all()
    sold = db.scalar(select(func.coalesce(func.sum(models.HarvestListing.committed_bunches), 0))) or 0
    return {
        "open_listings": len(listings),
        "open_requirements": len(reqs),
        "bunches_committed": int(sold),
        "note": "Committed bunches come from accepted early orders, so this shows how much supply is already spoken for.",
    }


# --------------------------------------------------------------------------
# 5.4 orders
# --------------------------------------------------------------------------


def next_order_reference(db: Session) -> str:
    """Collision-proof human reference, e.g. MS-EO-2026-0042."""
    from datetime import date as _date

    highest = db.scalar(select(func.max(models.EarlyOrder.id))) or 0
    while True:
        highest += 1
        ref = f"MS-EO-{_date.today():%Y}-{highest:04d}"
        exists = db.scalar(select(models.EarlyOrder.id).where(models.EarlyOrder.reference == ref))
        if not exists:
            return ref


def order_view(db: Session, order: models.EarlyOrder) -> dict:
    terms = earlyorders.OrderTerms(
        quantity_bunches=order.quantity_bunches,
        price_per_bunch_ugx=order.agreed_price_ugx_per_bunch,
        deposit_pct=order.deposit_pct,
        commission_pct=order.commission_pct,
    )
    snap = order.terms_snapshot or {}
    return {
        "id": order.id,
        "reference": order.reference,
        "status": order.status,
        "quantity_bunches": order.quantity_bunches,
        "price_per_bunch_ugx": order.agreed_price_ugx_per_bunch,
        "total_value_ugx": terms.total_value_ugx,
        "deposit_pct": order.deposit_pct,
        "advance_ugx": snap.get("advance_ugx", terms.advance_ugx),
        "advance_paid_ugx": order.advance_paid_ugx,
        "balance_due_ugx": order.balance_due_ugx,
        "service_fee_ugx": order.service_fee_ugx,
        "farmer_net_ugx": terms.farmer_net_ugx,
        "delivery_date": order.delivery_date,
        "grade": order.grade,
        "cancellation_rule": order.cancellation_rule,
        "crop_failure_declared": order.crop_failure_declared,
        "farmer": order.listing.seller.full_name if order.listing and order.listing.seller else None,
        "buyer": order.requirement.buyer.full_name if order.requirement and order.requirement.buyer else None,
        "district": order.listing.district if order.listing else None,
        "events": [{"at": e.at, "actor": e.actor, "kind": e.kind, "note": e.note} for e in order.events],
        "next_actions": sorted(earlyorders.TRANSITIONS.get(order.status, set())),
        "payment_note": snap.get(
            "payment_note",
            "Advance and balance move between the parties through an authorised payment partner.",
        ),
    }


# --------------------------------------------------------------------------
# 5.6 opportunities
# --------------------------------------------------------------------------


def opportunity_list(
    db: Session, *, district: str | None = None, kind: str | None = None, only_current: bool = True
) -> list[dict]:
    rows = db.scalars(select(models.Opportunity)).all()
    items = [
        {
            "id": o.id,
            "title": o.title,
            "summary": o.summary,
            "kind": o.kind,
            "source_name": o.source_name,
            "source_url": o.source_url,
            "eligibility": o.eligibility,
            "how_to_apply": o.how_to_apply,
            "districts": o.districts,
            "opens_on": o.opens_on,
            "deadline": o.deadline,
            "verified_on": o.verified_on,
            "verified_by": o.verified_by,
            "is_verified": o.is_verified,
            "status": o.status,
        }
        for o in rows
    ]
    out = opportunities.filter_for(items, district=district, kind=kind, only_current=only_current)
    for i in out:
        i["source_line"] = opportunities.source_line(i)
    return out


def tier_info() -> list[dict]:
    return entitlements.tier_matrix()
