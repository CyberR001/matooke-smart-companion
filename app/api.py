"""JSON API (the layer a mobile app or SMS bridge would call)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas, services
from .config import settings
from .db import get_db
from .engine import diseases, earlyorders, entitlements, products
from .engine.prices import series_for_chart

router = APIRouter(prefix="/api/v1", tags=["matookesmart"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    has_prices = (
        db.scalar(select(models.PriceRecord).with_only_columns(models.PriceRecord.id).limit(1)) is not None
    )
    return {
        "status": "ok",
        "app": settings.app_name,
        "has_price_history": has_prices,
        "data_disclaimer": settings.data_disclaimer,
    }


@router.get("/markets")
def markets(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for m in db.scalars(
        select(models.Market).where(models.Market.is_active.is_(True)).order_by(models.Market.name)
    ):
        last = services.latest_price(db, m.id)
        out.append(
            {
                "id": m.id,
                "name": m.name,
                "district": m.district,
                "unit": m.unit,
                "latest_price_ugx": last.price_ugx if last else None,
                "latest_date": last.observed_on if last else None,
                "synthetic": bool(last.is_synthetic) if last else True,
            }
        )
    return out


@router.get("/markets/{market_id}/prices")
def market_prices(
    market_id: int,
    days: int = Query(365, ge=7, le=1200),
    db: Session = Depends(get_db),
) -> dict:
    m = db.get(models.Market, market_id)
    if not m:
        raise HTTPException(404, "Unknown market")
    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(models.PriceRecord)
        .where(models.PriceRecord.market_id == market_id, models.PriceRecord.observed_on >= since)
        .order_by(models.PriceRecord.observed_on)
    ).all()
    return {
        "market": {"id": m.id, "name": m.name, "district": m.district, "unit": m.unit},
        "prices": [
            {
                "date": r.observed_on,
                "price_ugx": r.price_ugx,
                "grade": r.grade,
                "quantity_observed": r.quantity_observed,
                "source": r.source,
                "verified": r.verified,
                "synthetic": r.is_synthetic,
            }
            for r in rows
        ],
    }


@router.post("/prices", status_code=201)
def record_price(payload: schemas.PriceRecordIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(models.Market, payload.market_id):
        raise HTTPException(404, "Unknown market")
    row = models.PriceRecord(**payload.model_dump(), is_synthetic=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "message": (
            "Recorded. The value is marked unverified until a supervisor checks it; "
            "unverified rows do not raise forecast confidence."
        ),
    }


@router.get("/markets/{market_id}/forecast")
def market_forecast(
    market_id: int,
    horizon_days: int = Query(60, ge=7, le=180),
    with_chart: bool = Query(True),
    db: Session = Depends(get_db),
) -> dict:
    m = db.get(models.Market, market_id)
    if not m:
        raise HTTPException(404, "Unknown market")
    fc = services.forecast_for_market(db, market_id, horizon_days=horizon_days)
    db.add(
        models.ForecastRun(
            market_id=market_id,
            horizon_days=horizon_days,
            method=fc.method,
            mape_pct=fc.mape_pct,
            confidence=fc.confidence,
            payload={"n_records": fc.n_records, "trend_pct_per_month": fc.trend_pct_per_month},
        )
    )
    db.commit()
    points = services.price_points(db, market_id)
    d = {
        "market": fc.market_name,
        "unit": fc.unit,
        "generated_on": fc.generated_on,
        "n_records": fc.n_records,
        "n_verified": fc.n_verified,
        "span_days": fc.span_days,
        "latest_price_ugx": fc.latest_price_ugx,
        "latest_day": fc.latest_day,
        "ma7_ugx": fc.ma7_ugx,
        "ma28_ugx": fc.ma28_ugx,
        "trend_pct_per_month": fc.trend_pct_per_month,
        "seasonal_index": fc.seasonal_index,
        "mape_pct": fc.mape_pct,
        "confidence": fc.confidence,
        "method": fc.method,
        "caveats": fc.caveats,
        "summary": fc.summary(),
        "data_is_synthetic": fc.data_is_synthetic,
        "points": [
            {
                "date": p.day,
                "predicted_ugx": p.predicted_ugx,
                "low_ugx": p.low_ugx,
                "high_ugx": p.high_ugx,
                "season_note": p.season_note,
            }
            for p in fc.points
        ],
    }
    if with_chart:
        d["chart"] = series_for_chart(fc, points)
    return d


@router.get("/farms/{farm_id}/advice")
def farm_advice(
    farm_id: int,
    urgent_need_ugx: int = Query(0, ge=0),
    quantity_bunches: int | None = Query(None, ge=1),
    harvest_date: date | None = Query(None),
    horizon_days: int = Query(60, ge=7, le=180),
    db: Session = Depends(get_db),
) -> dict:
    farm = db.get(models.Farm, farm_id)
    if not farm:
        raise HTTPException(404, "Unknown farm")
    v = services.advice_for_farm(
        db,
        farm,
        urgent_need_ugx=urgent_need_ugx,
        horizon_days=horizon_days,
        quantity_bunches=quantity_bunches,
        harvest_date=harvest_date,
    )
    advice = v["advice"]
    return {
        "farm": {
            "id": farm.id,
            "name": farm.name,
            "district": farm.district,
            "expected_harvest_date": farm.expected_harvest_date,
            "matooke_stands": farm.matooke_stands,
        },
        "market": {"id": v["market"].id, "name": v["market"].name} if v["market"] else None,
        "listing": None
        if not v["listing"]
        else {
            "id": v["listing"].id,
            "quantity_bunches": v["listing"].quantity_bunches,
            "expected_harvest_date": v["listing"].expected_harvest_date,
            "asking_price_ugx_per_bunch": v["listing"].asking_price_ugx_per_bunch,
            "quantity_confidence": v["listing"].quantity_confidence,
        },
        "fresh_kg_assumed": v["fresh_kg_assumed"],
        "kg_per_bunch": v["kg_per_bunch"],
        "hub_note": v["hub_note"],
        "advice": advice.to_dict(),
        "recommendations": v["recommendations"],
    }


@router.get("/doctor/questions")
def doctor_questions() -> dict:
    return {
        "questions": [
            {
                "id": q["id"],
                "text": q["text"],
                "options": [{"id": o["id"], "label": o["label"]} for o in q["options"]],
            }
            for q in diseases.questions()
        ],
        "disclaimer": diseases.kb()["disclaimer"],
        "conditions_covered": [
            {"key": c["key"], "name": c["name"], "type": c["type"]} for c in diseases.conditions()
        ],
        "image_model": (
            "Image recognition is not enabled in this build. Upload is accepted for the record "
            "and for later expert review; the ranking comes from your answers."
        ),
    }


@router.post("/doctor/assess")
def doctor_assess(payload: schemas.DoctorAskIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(models.Person, payload.farmer_id):
        raise HTTPException(404, "Unknown farmer")
    result = services.doctor_assess(payload.answers, image_provided=payload.image_provided)
    case = models.DiseaseCase(
        farmer_id=payload.farmer_id,
        farm_id=payload.farm_id,
        answers=payload.answers,
        candidates=[
            {"key": c["key"], "name": c["name"], "confidence": c["confidence"]} for c in result["candidates"]
        ],
        top_confidence=result["confidence"],
        referred=result["referred"],
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    result["case_id"] = case.id
    result["recorded"] = "Saved to your farm record so an extension worker can see what you reported."
    return result


@router.post("/doctor/feedback", status_code=201)
def doctor_feedback(case_id: int, payload: schemas.FeedbackIn, db: Session = Depends(get_db)) -> dict:
    case = db.get(models.DiseaseCase, case_id)
    if not case:
        raise HTTPException(404, "Unknown case")
    case.farmer_rating = payload.rating
    db.commit()
    return {
        "saved": True,
        "why": "Usefulness ratings tell us whether the advice is understandable (section 10 metric).",
    }


@router.get("/products/recommend")
def product_recommend(
    fresh_kg: float = Query(500, gt=0),
    services_list: str = Query(
        "", description="comma separated: dryer,mill,fryer,cold_chain,partner_processor"
    ),
    db: Session = Depends(get_db),
) -> dict:
    svc = {s.strip() for s in services_list.split(",") if s.strip()}
    recs = services.product_recommendations(db, fresh_kg=fresh_kg, services=svc)
    return {
        "fresh_kg": fresh_kg,
        "bunches_approx": round(fresh_kg / 27.0, 1),
        "recommendations": recs,
        "notice": products.catalog()["notice"],
    }


@router.get("/products/{key}/economics")
def product_economics(
    key: str,
    fresh_kg: float = Query(500, gt=0),
    target_output_kg: float | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        products.product_spec(key)
    except KeyError:
        raise HTTPException(404, "Unknown product") from None
    econ = products.estimate_economics(
        key,
        fresh_kg=fresh_kg if not target_output_kg else None,
        target_output_kg=target_output_kg,
        trial=services.measured_trials(db).get(key),
    )
    return {
        "product": econ.product_name,
        "source": econ.source,
        "fresh_kg": econ.fresh_kg,
        "output_kg": econ.output_kg,
        "yield_pct": econ.yield_pct,
        "revenue_ugx": econ.revenue_ugx,
        "costs": {k: v for k, v in asdict(econ.costs).items() if v},
        "cost_total_ugx": econ.costs.total,
        "margin_ugx": econ.margin_ugx,
        "margin_pct": econ.margin_pct,
        "notes": econ.notes,
        "steps": products.product_spec(key)["process_steps"],
        "food_safety": products.product_spec(key)["food_safety"],
    }


@router.get("/products/{key}/income-target")
def product_income_target(
    key: str,
    target_income_ugx: int = Query(400000, gt=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        products.product_spec(key)
    except KeyError:
        raise HTTPException(404, "Unknown product") from None
    return products.fresh_kg_needed_for_income(
        key, target_income_ugx, trial=services.measured_trials(db).get(key)
    )


@router.post("/trials", status_code=201)
def add_trial(payload: schemas.TrialIn, db: Session = Depends(get_db)) -> dict:
    try:
        products.product_spec(payload.product_key)
    except KeyError:
        raise HTTPException(404, "Unknown product") from None
    if payload.output_kg > payload.fresh_input_kg:
        raise HTTPException(422, "Output weight cannot exceed fresh input weight.")
    t = models.ProductTrial(
        **payload.model_dump(exclude={"trial_date"}), trial_date=payload.trial_date or date.today()
    )
    db.add(t)
    db.commit()
    return {
        "id": t.id,
        "yield_pct": round(payload.output_kg / payload.fresh_input_kg * 100, 1),
        "message": "Trial recorded. Its measured yield and costs now override the catalog assumption for this product.",
    }


@router.get("/listings")
def listings(district: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = select(models.HarvestListing).order_by(models.HarvestListing.expected_harvest_date)
    if district:
        q = q.where(models.HarvestListing.district == district)
    return [
        {
            "id": row.id,
            "farmer": row.seller.full_name if row.seller else None,
            "district": row.district,
            "quantity_bunches": row.quantity_bunches,
            "committed_bunches": row.committed_bunches,
            "available_bunches": max(row.quantity_bunches - row.committed_bunches, 0),
            "expected_harvest_date": row.expected_harvest_date,
            "asking_price_ugx_per_bunch": row.asking_price_ugx_per_bunch,
            "grade": row.grade,
            "quantity_confidence": row.quantity_confidence,
            "notes": row.notes,
            "status": row.status,
        }
        for row in db.scalars(q)
    ]


@router.post("/listings", status_code=201)
def create_listing(payload: schemas.ListingIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(models.Person, payload.seller_id):
        raise HTTPException(404, "Unknown farmer")
    if payload.expected_harvest_date < date.today():
        raise HTTPException(422, "Expected harvest date is in the past.")
    row = models.HarvestListing(**payload.model_dump(), status="open")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "message": "Listing posted. Buyers searching for future supply can now see it."}


@router.get("/requirements")
def requirements(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": r.id,
            "buyer": r.buyer.full_name if r.buyer else None,
            "organisation": r.organisation,
            "district": r.district,
            "quantity_bunches": r.quantity_bunches,
            "needed_by": r.needed_by,
            "is_recurring_weekly": r.is_recurring_weekly,
            "min_grade": r.min_grade,
            "max_price_ugx_per_bunch": r.max_price_ugx_per_bunch,
            "willing_deposit_pct": r.willing_deposit_pct,
            "notes": r.notes,
            "status": r.status,
        }
        for r in db.scalars(select(models.BuyerRequirement).order_by(models.BuyerRequirement.needed_by))
    ]


@router.post("/requirements", status_code=201)
def create_requirement(payload: schemas.RequirementIn, db: Session = Depends(get_db)) -> dict:
    if not db.get(models.Person, payload.buyer_id):
        raise HTTPException(404, "Unknown buyer")
    r = models.BuyerRequirement(**payload.model_dump(), status="open")
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "message": "Requirement posted. We will match it against open listings."}


@router.get("/matches")
def matches(min_score: float = Query(0.35, ge=0, le=1), db: Session = Depends(get_db)) -> dict:
    suggestions = services.match_suggestions(db, min_score=min_score)
    return {"count": len(suggestions), "suggestions": suggestions, "market": services.unmatched_report(db)}


@router.post("/matches/run", status_code=201)
def run_matches(db: Session = Depends(get_db)) -> dict:
    suggestions = services.match_suggestions(db, persist=True)
    return {
        "created": len(suggestions),
        "message": "Suggested pairs recorded so we can measure how many get taken up (section 10 metric).",
    }


@router.post("/orders", status_code=201)
def create_order(payload: schemas.OrderCreateIn, db: Session = Depends(get_db)) -> dict:
    listing = db.get(models.HarvestListing, payload.listing_id)
    req = db.get(models.BuyerRequirement, payload.requirement_id)
    if not listing or not req:
        raise HTTPException(404, "Listing or requirement not found")
    available = listing.quantity_bunches - listing.committed_bunches
    if payload.quantity_bunches > available:
        raise HTTPException(422, f"Only {available} bunches are still uncommitted on that listing.")
    terms, notes = earlyorders.normalise_terms(
        quantity_bunches=payload.quantity_bunches,
        price_per_bunch_ugx=payload.price_per_bunch_ugx,
        deposit_pct=payload.deposit_pct,
        commission_pct=payload.commission_pct,
    )
    delivery = payload.delivery_date or (listing.expected_harvest_date + timedelta(days=2))
    ref = services.next_order_reference(db)
    try:
        order = earlyorders.build_order(
            reference=ref,
            listing_id=listing.id,
            requirement_id=req.id,
            terms=terms,
            delivery_date=delivery,
            grade=payload.grade,
            harvest_estimate_confidence=listing.quantity_confidence,
            cancellation_rule=payload.cancellation_rule,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    row = models.EarlyOrder(**order)
    db.add(row)
    db.flush()
    db.add(
        models.OrderEvent(
            order_id=row.id, kind="proposed", actor="platform", note=" ".join(notes) or "Terms drafted."
        )
    )
    db.commit()
    db.refresh(row)
    return {"reference": row.reference, "order": services.order_view(db, row), "adjustments": notes}


@router.get("/orders")
def orders(status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = select(models.EarlyOrder).order_by(models.EarlyOrder.id.desc())
    if status:
        q = q.where(models.EarlyOrder.status == status)
    return [services.order_view(db, o) for o in db.scalars(q)]


@router.get("/orders/{reference}")
def order(reference: str, db: Session = Depends(get_db)) -> dict:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order reference")
    return services.order_view(db, row)


@router.post("/orders/{reference}/transition")
def order_transition(reference: str, payload: schemas.OrderActionIn, db: Session = Depends(get_db)) -> dict:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order reference")
    try:
        new_status, message = earlyorders.transition(row.status, payload.action)
    except earlyorders.InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from None
    if payload.action == "request_deposit":
        row.advance_paid_ugx = (row.terms_snapshot or {}).get("advance_ugx", 0)
    if payload.action == "settle":
        row.balance_due_ugx = 0
    row.status = new_status
    db.add(models.OrderEvent(order_id=row.id, kind=payload.action, actor=payload.actor, note=payload.note))
    db.commit()
    db.refresh(row)
    return {"message": message, "order": services.order_view(db, row)}


@router.post("/orders/{reference}/settle")
def order_settle(reference: str, payload: schemas.SettleIn, db: Session = Depends(get_db)) -> dict:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order reference")
    if row.status not in {"delivered", "ready_for_delivery", "disputed", "in_growth"}:
        raise HTTPException(409, f"Cannot settle an order in status '{row.status}'. Record delivery first.")
    terms = earlyorders.OrderTerms(
        quantity_bunches=row.quantity_bunches,
        price_per_bunch_ugx=row.agreed_price_ugx_per_bunch,
        deposit_pct=row.deposit_pct,
        commission_pct=row.commission_pct,
    )
    result = earlyorders.settle(
        terms, delivered_bunches=payload.delivered_bunches, advance_paid_ugx=row.advance_paid_ugx
    )
    row.balance_due_ugx = 0
    row.service_fee_ugx = result["service_fee_ugx"]
    row.terms_snapshot = {**(row.terms_snapshot or {}), "settlement": result}
    row.status = "settled"
    db.add(
        models.OrderEvent(
            order_id=row.id,
            kind="settled",
            actor="platform",
            note=" | ".join(result["lines"]),
        )
    )
    if row.listing:
        row.listing.status = "fulfilled" if result["shortfall_bunches"] == 0 else "partially_fulfilled"
    db.commit()
    return result


@router.post("/orders/{reference}/crop-failure")
def crop_failure(reference: str, verified: bool = False, db: Session = Depends(get_db)) -> dict:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order reference")
    plan = earlyorders.declare_crop_failure(
        order_status=row.status,
        verified=verified,
        days_to_delivery=(row.delivery_date - date.today()).days,
    )
    row.crop_failure_declared = True
    db.add(models.OrderEvent(order_id=row.id, kind="crop_failure", actor="farmer", note=plan["recommended"]))
    db.commit()
    return plan


@router.get("/opportunities")
def opps(district: str | None = None, kind: str | None = None, db: Session = Depends(get_db)) -> dict:
    items = services.opportunity_list(db, district=district, kind=kind)
    return {
        "count": len(items),
        "items": items,
        "rule": "Only verified, in-date notices are shown as current. Anything unverified or stale is labelled.",
    }


@router.get("/hub/notices")
def hub_notices(db: Session = Depends(get_db)) -> dict:
    notices = services.live_hub_notices(db)
    return {
        "count": len(notices),
        "notices": notices,
        "policy": "The Hub buys against confirmed demand and sets a purchase limit per lot to protect working capital.",
    }


@router.get("/tiers")
def tiers() -> dict:
    return {
        "tiers": services.tier_info(),
        "never_gated": sorted(entitlements.SAFETY_CRITICAL),
        "note": "Prices are validation hypotheses, not tariffs (section 5.7).",
    }


@router.get("/dashboard")
def dashboard(
    farm_id: int = Query(1), urgent_need_ugx: int = Query(0, ge=0), db: Session = Depends(get_db)
) -> dict:
    farm = db.get(models.Farm, farm_id)
    if not farm:
        raise HTTPException(404, "Unknown farm")
    v = services.advice_for_farm(db, farm, urgent_need_ugx=urgent_need_ugx)
    fc = v["forecast"]
    recent_cases = db.scalars(
        select(models.DiseaseCase)
        .where(models.DiseaseCase.farmer_id == farm.owner_id)
        .order_by(models.DiseaseCase.id.desc())
        .limit(3)
    ).all()
    orders = db.scalars(select(models.EarlyOrder).order_by(models.EarlyOrder.id.desc()).limit(4)).all()
    return {
        "farmer": farm.owner.full_name,
        "tier": farm.owner.tier,
        "farm": {"id": farm.id, "name": farm.name, "district": farm.district, "stands": farm.matooke_stands},
        "market": {"id": fc.market_name},
        "price": {
            "latest_ugx": fc.latest_price_ugx,
            "latest_day": fc.latest_day,
            "confidence": fc.confidence,
            "summary": fc.summary(),
            "mape_pct": fc.mape_pct,
            "data_is_synthetic": fc.data_is_synthetic,
        },
        "harvest": {
            "expected": farm.expected_harvest_date,
            "in_days": (farm.expected_harvest_date - date.today()).days
            if farm.expected_harvest_date
            else None,
        },
        "alerts": v["advice"].alerts,
        "headline": v["advice"].headline,
        "primary_option": v["advice"].primary_option,
        "opportunities": services.opportunity_list(db, district=farm.district)[:3],
        "hub_notices": services.live_hub_notices(db)[:2],
        "orders": [services.order_view(db, o) for o in orders],
        "cases": [
            {
                "id": c.id,
                "at": c.created_at,
                "referred": c.referred,
                "top_confidence": c.top_confidence,
                "expert_outcome": c.expert_outcome,
            }
            for c in recent_cases
        ],
        "disclaimer": settings.data_disclaimer,
    }
