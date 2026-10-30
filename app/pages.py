"""Server-rendered mobile-first screens (concept proposal section 16).

Forms are plain POSTs rather than JavaScript calls, so every screen still
works on a cheap phone, on a flaky connection, or with scripts blocked.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, services
from .charts import price_chart_svg
from .config import settings
from .db import get_db
from .engine import diseases, earlyorders, entitlements, products
from .engine.prices import series_for_chart

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
router = APIRouter()

templates.env.filters["ugx"] = lambda v: f"{int(v or 0):,} UGX"
templates.env.filters["day"] = lambda v: v.strftime("%d %b %Y") if v else "-"
templates.env.filters["short"] = lambda v: v.strftime("%d %b") if v else "-"
templates.env.filters["pct"] = lambda v: f"{float(v or 0):.1f} %"


def _pricechart(chart: dict, **kw):
    return price_chart_svg(chart, **kw)


templates.env.filters["pricechart"] = _pricechart


def ctx(request: Request, **kw) -> dict:
    return {
        "request": request,
        "app_name": settings.app_name,
        "tagline": settings.tagline,
        "disclaimer": settings.data_disclaimer,
        "today": date.today(),
        "nav": [
            ("/", "Overview"),
            ("/dashboard", "Farmer home"),
            ("/farm-doctor", "Farm doctor"),
            ("/when-to-sell", "When to sell"),
            ("/early-orders", "Early orders"),
            ("/marketplace", "Marketplace"),
            ("/hub", "Hub & products"),
            ("/opportunities", "Opportunities"),
            ("/prices", "Price log"),
            ("/tiers", "Membership"),
            ("/system", "How it fits"),
        ],
        **kw,
    }


def _int(value: str | int | None, default: int = 0) -> int:
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (TypeError, ValueError):
        return default


def _date(value: str | None, default: date | None = None) -> date | None:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


def farms_with_owner(db: Session) -> list[models.Farm]:
    return list(db.scalars(select(models.Farm).order_by(models.Farm.id)))


@router.get("/", response_class=HTMLResponse)
def overview(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    markets = []
    for m in db.scalars(
        select(models.Market).where(models.Market.is_active.is_(True)).order_by(models.Market.name)
    ):
        last = services.latest_price(db, m.id)
        markets.append(
            {
                "name": m.name,
                "district": m.district,
                "unit": m.unit,
                "latest_price_ugx": last.price_ugx if last else None,
                "latest_date": last.observed_on if last else None,
                "verified": bool(last.verified) if last else False,
            }
        )

    def _count(stmt) -> int:
        return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    counts = {
        "farmers": _count(select(models.Person).where(models.Person.role == "farmer")),
        "buyers": _count(select(models.Person).where(models.Person.role == "buyer")),
        "markets": len(markets),
        "price_records": int(db.scalar(select(func.count(models.PriceRecord.id))) or 0),
        "open_orders": _count(
            select(models.EarlyOrder).where(models.EarlyOrder.status.notin_(["settled", "cancelled"]))
        ),
    }
    modules = [
        (
            "5.1",
            "Farm doctor",
            "Guided symptom questions against an expert-reviewable knowledge base; possible diagnosis, confidence, referral when unsure.",
            "/farm-doctor",
        ),
        (
            "5.2",
            "When to sell",
            "Moving averages, shrunk seasonal indices and a backtested trend give a price outlook plus ranked options - not just a chart.",
            "/when-to-sell",
        ),
        (
            "5.3",
            "Surplus & products",
            "Processing yield, cost stack, margin and an explainable product ranking; measured trials override assumptions.",
            "/hub",
        ),
        (
            "5.4",
            "Early orders",
            "Advance-purchase agreements with deposit, balance, disclosed fee, cancellation and crop-failure terms.",
            "/early-orders",
        ),
        (
            "5.5",
            "Marketplace matching",
            "Greedy, explainable matching on distance, quantity, timing, grade and price.",
            "/marketplace",
        ),
        (
            "5.6",
            "Opportunities",
            "Verified government and partner support with source, check date and expiry rules.",
            "/opportunities",
        ),
        (
            "5.7",
            "Membership",
            "Four tiers, with safety-critical information exempt from every paywall.",
            "/tiers",
        ),
    ]
    return templates.TemplateResponse(
        request, "overview.html", ctx(request, modules=modules, counts=counts, markets=markets)
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    farm_id: int = 1,
    urgent: int = 0,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    # Never fall back to somebody else's farm: that would show another farmer's
    # holdings and prices to the wrong person.
    farm = db.get(models.Farm, farm_id)
    if not farm:
        raise HTTPException(404, "No such farm in this demo dataset")
    v = services.advice_for_farm(db, farm, urgent_need_ugx=urgent)
    fc = v["forecast"]
    advice = v["advice"]
    cases = list(
        db.scalars(
            select(models.DiseaseCase)
            .where(models.DiseaseCase.farmer_id == farm.owner_id)
            .order_by(models.DiseaseCase.id.desc())
            .limit(3)
        )
    )
    orders = [
        services.order_view(db, o)
        for o in db.scalars(select(models.EarlyOrder).order_by(models.EarlyOrder.id.desc()).limit(3))
    ]
    opps = services.opportunity_list(db, district=farm.district)[:3]
    hub = services.live_hub_notices(db)[:2]
    matches = services.match_suggestions(db)[:3]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        ctx(
            request,
            farm=farm,
            farms=farms_with_owner(db),
            forecast=fc,
            advice=advice,
            market=v["market"],
            cases=cases,
            orders=orders,
            opportunities=opps,
            hub_notices=hub,
            matches=matches,
            chart=series_for_chart(fc, services.price_points(db, v["market"].id)),
            fresh_kg=v["fresh_kg_assumed"],
        ),
    )


def _parse_answers(answers: str) -> dict[str, str]:
    """Accepts either 'qid:opt;qid:opt' or plain ?qid=opt query params."""
    parsed: dict[str, str] = {}
    for chunk in (answers or "").split(";"):
        if ":" in chunk:
            k, val = chunk.split(":", 1)
            parsed[k] = val
    return parsed


@router.get("/farm-doctor", response_class=HTMLResponse)
def farm_doctor(
    request: Request,
    farmer_id: int = 1,
    answers: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    known = {q["id"] for q in diseases.questions()}
    parsed = _parse_answers(answers)
    for key, value in request.query_params.items():
        if key in known and value:
            parsed[key] = value
    result = services.doctor_assess(parsed, image_provided=False)
    people = list(
        db.scalars(select(models.Person).where(models.Person.role == "farmer").order_by(models.Person.id))
    )
    return templates.TemplateResponse(
        request,
        "farm_doctor.html",
        ctx(
            request,
            people=people,
            farmer_id=farmer_id,
            questions=diseases.questions(),
            answers=parsed,
            result=result,
            conditions=diseases.conditions(),
            kb_disclaimer=diseases.kb()["disclaimer"],
            referral_floor=settings.disease_referral_confidence,
        ),
    )


@router.post("/farm-doctor/save", response_class=HTMLResponse)
async def farm_doctor_save(
    request: Request,
    farmer_id: int = Form(...),
    answers: str = Form(""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    parsed = _parse_answers(answers)
    result = services.doctor_assess(parsed)
    case = models.DiseaseCase(
        farmer_id=_int(farmer_id),
        answers=parsed,
        candidates=[
            {"key": c["key"], "name": c["name"], "confidence": c["confidence"]} for c in result["candidates"]
        ],
        top_confidence=result["confidence"],
        referred=result["referred"],
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return templates.TemplateResponse(
        request,
        "message.html",
        ctx(
            request,
            title=f"Case {case.id} saved to your farm record",
            message=(
                "Saved so an extension worker can see exactly what you reported and when. "
                + (
                    "This case was flagged for referral - bring the reference number to the "
                    "parish agricultural office."
                    if case.referred
                    else "No referral was needed, but keep observing the plants this week."
                )
            ),
            back="/farm-doctor",
        ),
    )


@router.get("/when-to-sell", response_class=HTMLResponse)
def when_to_sell(
    request: Request,
    farm_id: int = 1,
    horizon: int = 60,
    urgent: int = 0,
    quantity: int | None = None,
    harvest: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    farm = db.get(models.Farm, farm_id)
    if not farm:
        raise HTTPException(404, "No such farm in this demo dataset")
    farms = farms_with_owner(db)
    v = services.advice_for_farm(
        db,
        farm,
        urgent_need_ugx=urgent,
        horizon_days=max(7, min(int(horizon), 180)),
        quantity_bunches=quantity,
        harvest_date=_date(harvest),
    )
    advice = v["advice"]
    market = v["market"]
    return templates.TemplateResponse(
        request,
        "when_to_sell.html",
        ctx(
            request,
            farm=farm,
            farms=farms,
            market=market,
            forecast=v["forecast"],
            advice=advice,
            options=advice.options,
            chart=series_for_chart(v["forecast"], services.price_points(db, market.id)),
            recommendations=v["recommendations"][:3],
            hub_note=v["hub_note"],
            fresh_kg=v["fresh_kg_assumed"],
            kg_per_bunch=v["kg_per_bunch"],
            horizon=horizon,
            urgent=urgent,
            quantity=quantity or "",
            harvest=harvest or "",
        ),
    )


@router.get("/marketplace", response_class=HTMLResponse)
def marketplace(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    suggestions = services.match_suggestions(db)
    listings = [
        {
            "id": row.id,
            "farmer": row.seller.full_name if row.seller else "-",
            "district": row.district,
            "quantity_bunches": row.quantity_bunches,
            "available": max(row.quantity_bunches - row.committed_bunches, 0),
            "harvest": row.expected_harvest_date,
            "price": row.asking_price_ugx_per_bunch,
            "grade": row.grade,
            "confidence": row.quantity_confidence,
            "status": row.status,
            "notes": row.notes,
        }
        for row in db.scalars(
            select(models.HarvestListing).order_by(models.HarvestListing.expected_harvest_date)
        )
    ]
    requirements = [
        {
            "id": r.id,
            "buyer": r.organisation or (r.buyer.full_name if r.buyer else "-"),
            "district": r.district,
            "quantity_bunches": r.quantity_bunches,
            "needed_by": r.needed_by,
            "max_price": r.max_price_ugx_per_bunch,
            "recurring": r.is_recurring_weekly,
            "deposit": r.willing_deposit_pct,
            "grade": r.min_grade,
            "status": r.status,
        }
        for r in db.scalars(select(models.BuyerRequirement).order_by(models.BuyerRequirement.needed_by))
    ]
    return templates.TemplateResponse(
        request,
        "marketplace.html",
        ctx(
            request,
            listings=listings,
            requirements=requirements,
            suggestions=suggestions,
            report=services.unmatched_report(db),
        ),
    )


@router.get("/early-orders", response_class=HTMLResponse)
def early_orders(
    request: Request,
    listing_id: int | None = None,
    requirement_id: int | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    orders = [
        services.order_view(db, o)
        for o in db.scalars(select(models.EarlyOrder).order_by(models.EarlyOrder.id.desc()))
    ]
    listings = list(db.scalars(select(models.HarvestListing).where(models.HarvestListing.status == "open")))
    reqs = list(db.scalars(select(models.BuyerRequirement).where(models.BuyerRequirement.status == "open")))
    return templates.TemplateResponse(
        request,
        "early_orders.html",
        ctx(
            request,
            orders=orders,
            listings=listings,
            requirements=reqs,
            prefill_listing=listing_id or (listings[0].id if listings else ""),
            prefill_req=requirement_id or (reqs[0].id if reqs else ""),
            statuses=sorted(earlyorders.TRANSITIONS),
            cancellation=earlyorders.DEFAULT_CANCELLATION_RULE,
            max_deposit=earlyorders.MAX_DEPOSIT_PCT,
        ),
    )


@router.post("/early-orders", response_class=HTMLResponse)
async def create_early_order(
    request: Request,
    listing_id: int = Form(...),
    requirement_id: int = Form(...),
    quantity_bunches: int = Form(...),
    price_per_bunch_ugx: int = Form(...),
    deposit_pct: float = Form(25.0),
    commission_pct: float = Form(3.0),
    delivery_date: str | None = Form(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    listing = db.get(models.HarvestListing, listing_id)
    req = db.get(models.BuyerRequirement, requirement_id)
    if not listing or not req:
        raise HTTPException(404, "Listing or requirement not found")
    terms, notes = earlyorders.normalise_terms(
        quantity_bunches=_int(quantity_bunches, 1),
        price_per_bunch_ugx=_int(price_per_bunch_ugx, 1),
        deposit_pct=deposit_pct,
        commission_pct=commission_pct,
    )
    delivery = _date(delivery_date) or (listing.expected_harvest_date + timedelta(days=2))
    ref = services.next_order_reference(db)
    try:
        payload = earlyorders.build_order(
            reference=ref,
            listing_id=listing.id,
            requirement_id=req.id,
            terms=terms,
            delivery_date=delivery,
            grade=listing.grade,
            harvest_estimate_confidence=listing.quantity_confidence,
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "message.html",
            ctx(request, title="Order not posted", message=str(exc), back="/early-orders"),
            status_code=422,
        )
    row = models.EarlyOrder(**payload)
    db.add(row)
    db.flush()
    db.add(
        models.OrderEvent(
            order_id=row.id,
            kind="proposed",
            actor="platform",
            note=" ".join(notes) or "Terms drafted from the matched listing.",
        )
    )
    listing.committed_bunches = min(
        listing.committed_bunches + row.quantity_bunches, listing.quantity_bunches
    )
    db.commit()
    return templates.TemplateResponse(
        request,
        "message.html",
        ctx(
            request,
            title=f"Draft order {ref} created",
            message=(
                "The order is in 'proposed'. Both parties must agree the terms before any deposit "
                "moves, and payments go through an authorised partner - MatookeSmart records the "
                "agreement, it does not hold the money and it is not lending."
            )
            + (" Adjustments applied: " + " ".join(notes) if notes else ""),
            back=f"/orders/{ref}",
        ),
    )


@router.get("/orders/{reference}", response_class=HTMLResponse)
def order_page(request: Request, reference: str, db: Session = Depends(get_db)) -> HTMLResponse:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order")
    view = services.order_view(db, row)
    terms = earlyorders.OrderTerms(
        quantity_bunches=row.quantity_bunches,
        price_per_bunch_ugx=row.agreed_price_ugx_per_bunch,
        deposit_pct=row.deposit_pct,
        commission_pct=row.commission_pct,
    )
    return templates.TemplateResponse(
        request,
        "order_detail.html",
        ctx(
            request,
            order=row,
            view=view,
            terms=terms,
            actions=sorted(earlyorders.ACTION_LABELS),
            next_status=sorted(earlyorders.TRANSITIONS.get(row.status, set())),
        ),
    )


@router.post("/orders/{reference}/action", response_class=HTMLResponse)
async def order_action(
    request: Request,
    reference: str,
    action: str = Form(...),
    actor: str = Form("farmer"),
    note: str | None = Form(None),
    delivered_bunches: int | None = Form(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    row = db.scalars(select(models.EarlyOrder).where(models.EarlyOrder.reference == reference)).first()
    if not row:
        raise HTTPException(404, "Unknown order")
    if delivered_bunches is not None and action == "settle":
        terms = earlyorders.OrderTerms(
            quantity_bunches=row.quantity_bunches,
            price_per_bunch_ugx=row.agreed_price_ugx_per_bunch,
            deposit_pct=row.deposit_pct,
            commission_pct=row.commission_pct,
        )
        res = earlyorders.settle(
            terms, delivered_bunches=_int(delivered_bunches), advance_paid_ugx=row.advance_paid_ugx
        )
        row.balance_due_ugx = 0
        row.service_fee_ugx = res["service_fee_ugx"]
        row.terms_snapshot = {**(row.terms_snapshot or {}), "settlement": res}
        row.status = "settled"
        db.add(models.OrderEvent(order_id=row.id, kind="settled", actor=actor, note=" | ".join(res["lines"])))
        db.commit()
        return RedirectResponse(f"/orders/{reference}", status_code=303)
    try:
        new_status, message = earlyorders.transition(row.status, action)
    except earlyorders.InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from None
    if action == "request_deposit":
        row.advance_paid_ugx = (row.terms_snapshot or {}).get("advance_ugx", 0)
    row.status = new_status
    db.add(
        models.OrderEvent(
            order_id=row.id, kind=action, actor=actor, note=(note or "") + f" [{message}]"
        ).strip()
        or message
    )
    db.commit()
    return RedirectResponse(f"/orders/{reference}", status_code=303)


@router.get("/opportunities", response_class=HTMLResponse)
def opportunities_page(
    request: Request, district: str | None = None, kind: str | None = None, db: Session = Depends(get_db)
) -> HTMLResponse:
    all_items = services.opportunity_list(db, only_current=False)
    shown = services.opportunity_list(db, district=district, kind=kind)
    hidden = [i for i in all_items if i["id"] not in {s["id"] for s in shown}]
    return templates.TemplateResponse(
        request,
        "opportunities.html",
        ctx(
            request,
            items=shown,
            held_back=hidden,
            districts=sorted({d for i in all_items for d in (i.get("districts") or [])}),
            kinds=sorted({i["kind"] for i in all_items}),
            district=district or "",
            kind=kind or "",
        ),
    )


@router.get("/hub", response_class=HTMLResponse)
def hub(
    request: Request,
    fresh_kg: int = 400,
    services_str: str = "dryer",
    target: int = 0,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    svc = {s.strip() for s in services_str.split(",") if s.strip()}
    recs = services.product_recommendations(db, fresh_kg=max(_int(fresh_kg, 400), 1), services=svc)
    trials = list(db.scalars(select(models.ProductTrial).order_by(models.ProductTrial.trial_date.desc())))
    notices = list(db.scalars(select(models.HubBuyingNotice)))
    income = None
    if target and recs:
        income = {
            "product": recs[0]["product_name"],
            "calc": products.fresh_kg_needed_for_income(
                recs[0]["product_key"],
                _int(target),
                trial=services.measured_trials(db).get(recs[0]["product_key"]),
            ),
        }
    return templates.TemplateResponse(
        request,
        "hub.html",
        ctx(
            request,
            recs=recs,
            trials=trials,
            notices=notices,
            fresh_kg=fresh_kg,
            services_str=services_str,
            target=target,
            income=income,
            notice=products.catalog()["notice"],
            cost_basis=products.catalog()["cost_basis"],
            all_services=["dryer", "mill", "fryer", "cold_chain", "partner_processor"],
        ),
    )


@router.get("/prices", response_class=HTMLResponse)
def prices_page(
    request: Request, market_id: int | None = None, db: Session = Depends(get_db)
) -> HTMLResponse:
    markets = list(db.scalars(select(models.Market).order_by(models.Market.name)))
    mid = market_id or (markets[0].id if markets else None)
    rows = []
    if mid:
        rows = list(
            db.scalars(
                select(models.PriceRecord)
                .where(models.PriceRecord.market_id == mid)
                .order_by(models.PriceRecord.observed_on.desc())
                .limit(30)
            )
        )
    return templates.TemplateResponse(
        request,
        "prices.html",
        ctx(request, markets=markets, market_id=mid, rows=rows),
    )


@router.post("/prices", response_class=HTMLResponse)
async def record_price(
    request: Request,
    market_id: int = Form(...),
    observed_on: str = Form(...),
    price_ugx: int = Form(...),
    grade: str = Form("medium"),
    source: str = Form("field agent"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    day = _date(observed_on, date.today())
    if day and day > date.today():
        return RedirectResponse("/prices?error=future", status_code=303)
    row = models.PriceRecord(
        market_id=_int(market_id),
        observed_on=day or date.today(),
        price_ugx=max(_int(price_ugx), 1),
        grade=grade,
        source=source,
        verified=False,
        is_synthetic=False,
        notes="Entered through the web form - awaiting supervisor check.",
    )
    db.add(row)
    db.commit()
    return RedirectResponse(f"/prices?market_id={market_id}&saved=1", status_code=303)


@router.get("/tiers", response_class=HTMLResponse)
def tiers_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "tiers.html",
        ctx(
            request,
            tiers=entitlements.TIERS,
            gated=entitlements.GATED,
            never_gated=sorted(entitlements.SAFETY_CRITICAL),
        ),
    )


@router.post("/admin/reseed", response_class=HTMLResponse)
def reseed(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Reset the demo dataset. Only meaningful while the data is synthetic."""
    from . import seed as seed_module

    report = seed_module.seed(db, force=True)
    return templates.TemplateResponse(
        request,
        "message.html",
        ctx(request, title="Demo data rebuilt", message=str(report), back="/"),
    )
