"""Demo seed data.

EVERY price, yield, cost and margin here is synthetic. The concept proposal is
explicit that the team must populate figures from real quotations and trials
rather than invent them (sections 5.2, 5.3, 14), so the generator marks all of
its rows `is_synthetic=True`, `verified=False` for most observations, and the UI
surfaces that label. Real pilots replace this file with field collection.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .db import SessionLocal, init_db

RNG_SEED = 20261030
WEEKS_BACK = 112

# Matooke seasonality used to shape the synthetic series (illustrative).
SEASON = {
    1: 1.16,
    2: 1.12,
    3: 1.02,
    4: 0.92,
    5: 0.88,
    6: 0.96,
    7: 1.05,
    8: 1.08,
    9: 0.94,
    10: 0.86,
    11: 0.90,
    12: 1.02,
}

MARKETS = [
    ("Nakasero Market", "Kampala", 0.3120, 32.5760, 34000),
    ("Kalerwe Market", "Kampala", 0.3730, 32.5910, 31000),
    ("Wakiso Central Market", "Wakiso", 0.4020, 32.4610, 27000),
    ("Kayunga Market", "Kayunga", 0.7560, 32.8960, 22000),
    ("Masaka Market", "Masaka", -0.3400, 31.7390, 24000),
    ("Fort Portal Market", "Kabarole", 0.6670, 30.2840, 19000),
]

FARMERS = [
    ("Nnalongo Aisha", "+256772114501", "Mukono", 0.3550, 32.7600, 140, 21),
    ("Ssekandi Boniface", "+256701442388", "Luwero", 1.8540, 32.4860, 220, 34),
    ("Nabbanja Grace", "+256758990221", "Kayunga", 0.7700, 32.9020, 90, 12),
    ("Tumusiime Patrick", "+256772660114", "Kabarole", 0.6500, 30.3100, 310, 45),
]

BUYERS = [
    ("St. Mary's College Naalya", "+256414600118", "Kampala", "buyer", "school meals", 260, 42000, True),
    ("Kasuku Restaurant", "+256772500331", "Kampala", "buyer", "restaurant", 90, 38000, False),
    ("Mama Ali Trading", "+256705112244", "Wakiso", "buyer", "wholesale trader", 400, 30000, False),
]


def _weeks(count: int) -> list[date]:
    today = date.today()
    # Anchor on Thursdays: the main matooke market day in several central markets.
    while today.weekday() != 3:
        today -= timedelta(days=1)
    return [today - timedelta(days=7 * i) for i in range(count - 1, -1, -1)]


def _make_series(rng: random.Random, base: int, phase: float) -> list[tuple[date, int]]:
    out: list[tuple[date, int]] = []
    for i, day in enumerate(_weeks(WEEKS_BACK)):
        seasonal = SEASON[day.month]
        trend = 1.0 + 0.020 * (i / 52.0)  # ~2 % a year drift
        wiggle = 1.0 + 0.03 * math.sin((i / 52.0) * 2 * math.pi + phase)
        noise = rng.uniform(0.92, 1.08)
        shock = 1.0
        if rng.random() < 0.05:  # road closure, festival, sudden glut
            shock = rng.uniform(0.80, 1.22)
        out.append((day, max(4000, int(base * seasonal * trend * wiggle * noise * shock))))
    return out


def seed(db: Session, *, force: bool = False) -> dict:
    existing = db.scalar(select(func.count()).select_from(models.Person))
    if existing and not force:
        return {"seeded": False, "reason": "database already has records"}
    if force:
        for table in (
            models.OrderEvent,
            models.EarlyOrder,
            models.MatchRun,
            models.HarvestListing,
            models.BuyerRequirement,
            models.DiseaseCase,
            models.PriceRecord,
            models.ForecastRun,
            models.ProductTrial,
            models.HubBuyingNotice,
            models.Opportunity,
            models.Subscription,
            models.Farm,
            models.Person,
            models.Market,
        ):
            db.query(table).delete()
        db.commit()

    rng = random.Random(RNG_SEED)
    today = date.today()

    markets = []
    for i, (name, district, lat, lng, base) in enumerate(MARKETS):
        m = models.Market(
            name=name, district=district, latitude=lat, longitude=lng, unit="bunch", is_active=True
        )
        db.add(m)
        db.flush()
        markets.append(m)
        # A per-market phase so the markets are not perfectly correlated.
        for j, (day, price) in enumerate(_make_series(rng, base, phase=i * 0.7)):
            db.add(
                models.PriceRecord(
                    market_id=m.id,
                    observed_on=day,
                    price_ugx=price,
                    quantity_observed=rng.randint(40, 400),
                    grade=rng.choice(["medium", "medium", "high", "low"]),
                    source="field agent log (synthetic)",
                    verified=j % 5 != 0,  # leave some unverified on purpose
                    is_synthetic=True,
                    notes=None,
                )
            )

    people: list[models.Person] = []
    for name, phone, district, lat, lng, stands, harvest_in_days in FARMERS:
        p = models.Person(
            full_name=name,
            phone=phone,
            district=district,
            role="farmer",
            tier="basic_farmer",
            consent_profile=True,
            consent_images=True,
            consent_contact=True,
        )
        db.add(p)
        db.flush()
        farm = models.Farm(
            owner_id=p.id,
            name=f"{name.split()[0]}'s garden",
            district=district,
            parish="sample parish",
            latitude=lat,
            longitude=lng,
            area_acres=round(rng.uniform(0.8, 3.5), 1),
            planting_date=today - timedelta(days=rng.randint(300, 480)),
            expected_harvest_date=today + timedelta(days=harvest_in_days),
            matooke_stands=stands,
            hands_per_bunch=float(rng.choice([15, 17, 18, 20])),
            variety="matooke (Nakitembe/Nakyabulamu type)",
            notes="De-leafed twice this season; male bud removal started on part of the mat.",
        )
        db.add(farm)
        people.append(p)
    db.flush()

    # One paid membership so the tier logic is visible in the demo.
    db.add(
        models.Subscription(
            person_id=people[1].id,
            tier="smart_farmer",
            amount_ugx=10000,
            price_is_hypothesis=True,
            status="active",
            started_on=today - timedelta(days=12),
            expires_on=today + timedelta(days=18),
        )
    )
    people[1].tier = "smart_farmer"

    buyer_people = []
    for name, phone, district, role, kind, qty, price, recurring in BUYERS:
        b = models.Person(
            full_name=name,
            phone=phone,
            district=district,
            role=role,
            tier="buyer_institution",
            consent_profile=True,
        )
        db.add(b)
        db.flush()
        buyer_people.append((b, kind, qty, price, recurring))

    hub_staff = models.Person(
        full_name="MatookeSmart Hub Operations",
        district="Wakiso",
        role="hub",
        tier="basic_farmer",
        consent_profile=True,
    )
    agent = models.Person(
        full_name="Field Agent 01", district="Mukono", role="staff", tier="basic_farmer", consent_profile=True
    )
    db.add_all([hub_staff, agent])
    db.flush()

    # --- future-supply listings -------------------------------------------
    for i, p in enumerate(people):
        farm = p.farms[0]
        bunches = max(int(farm.matooke_stands or 100) * 2 // 3, 30)
        db.add(
            models.HarvestListing(
                seller_id=p.id,
                farm_id=farm.id,
                district=farm.district,
                quantity_bunches=bunches,
                hands_per_bunch=farm.hands_per_bunch or 17.0,
                expected_harvest_date=today + timedelta(days=[21, 34, 12, 47][i]),
                quantity_confidence=["medium", "high", "low", "medium"][i],
                grade=["medium", "high", "medium", "medium"][i],
                asking_price_ugx_per_bunch=[33000, 36000, 30000, 28000][i],
                status="open",
                notes=[
                    None,
                    "Can split into two lots; transport available on Thursdays.",
                    "Bunches smaller than usual after the dry spell.",
                    "Neighbour's garden shows BXW symptoms - may harvest earlier.",
                ][i],
            )
        )

    # --- buyer requirements ------------------------------------------------
    for b, kind, qty, price, recurring in buyer_people:
        db.add(
            models.BuyerRequirement(
                buyer_id=b.id,
                organisation=kind,
                product="fresh_matooke",
                district=b.district,
                quantity_bunches=qty,
                needed_by=today + timedelta(days=14 if not recurring else 7),
                is_recurring_weekly=recurring,
                min_grade="medium",
                max_price_ugx_per_bunch=price,
                willing_deposit_pct=25.0 if recurring else 0.0,
                accepts_future_harvest=True,
                status="open",
                notes=(
                    "Needs delivery before Monday classes; will pay a deposit to lock weekly supply."
                    if recurring
                    else "Prefers Thursday delivery; accepts one supplier per week."
                ),
            )
        )
    db.flush()

    # --- one live early order, mid-flight ----------------------------------
    listing = db.scalars(select(models.HarvestListing).order_by(models.HarvestListing.id)).first()
    req = db.scalars(
        select(models.BuyerRequirement).where(models.BuyerRequirement.is_recurring_weekly.is_(True))
    ).first()
    if listing and req:
        qty = min(listing.quantity_bunches, req.quantity_bunches)
        price = min(listing.asking_price_ugx_per_bunch, req.max_price_ugx_per_bunch)
        total = qty * price
        advance = round(total * 0.25)
        order = models.EarlyOrder(
            reference=f"MS-EO-{today:%Y}-0001",
            listing_id=listing.id,
            requirement_id=req.id,
            quantity_bunches=qty,
            agreed_price_ugx_per_bunch=price,
            deposit_pct=25.0,
            advance_paid_ugx=advance,
            balance_due_ugx=total - advance,
            commission_pct=3.0,
            service_fee_ugx=round(total * 0.03),
            delivery_date=today + timedelta(days=19),
            grade=listing.grade,
            status="in_growth",
            terms_snapshot={
                "total_value_ugx": total,
                "advance_ugx": advance,
                "balance_ugx": total - advance,
                "service_fee_ugx": round(total * 0.03),
                "farmer_net_ugx": total - round(total * 0.03),
                "price_per_hand_ugx": round(price / 17.0, 1),
                "payment_note": (
                    "Advance and balance agreed between buyer and farmer through an authorised "
                    "payment partner. MatookeSmart records the order; it does not hold the money "
                    "and this is not a loan."
                ),
                "warnings": [],
            },
        )
        db.add(order)
        db.flush()
        for kind, actor, note in (
            ("proposed", "system", "Auto-matched from listing #1 and the school's weekly requirement."),
            ("terms_sent", "St. Mary's College Naalya", "Buyer accepted 25 % deposit, Thursday collection."),
            (
                "confirmed",
                "payment partner",
                "Deposit receipt 8842 recorded (external payment, not held by MatookeSmart).",
            ),
            ("in_growth", "system", "Farmer confirmed the mat is flowering and on schedule."),
        ):
            db.add(models.OrderEvent(order_id=order.id, kind=kind, actor=actor, note=note))
        listing.committed_bunches = qty

    # --- Hub buying notices -------------------------------------------------
    db.add_all(
        [
            models.HubBuyingNotice(
                title="Matooke flour feedstock and semi-processed chips",
                accepts="matooke_flour",
                accepts_form="dry sliced chips or clean fresh surplus",
                quality_spec=(
                    "Mature but not split fingers; no BXW symptoms; chips dried to <= 10 % moisture; "
                    "delivered in clean woven sacks, lot size >= 150 kg fresh"
                ),
                quantity_kg=900,
                price_basis="UGX per kg delivered",
                price_ugx_per_unit=760,
                district="Wakiso",
                pickup_point="Hub aggregation point, Kyengere",
                opens_on=today - timedelta(days=6),
                closes_on=today + timedelta(days=24),
                purchase_limit_kg=400,
                status="open",
            ),
            models.HubBuyingNotice(
                title="Dried chips for local market packs",
                accepts="dried_matooke_chips",
                accepts_form="farmer-dried chips",
                quality_spec="Even cream colour, no mould, snaps dry, sorted by size",
                quantity_kg=180,
                price_basis="UGX per kg delivered",
                price_ugx_per_unit=1450,
                district="Wakiso",
                pickup_point="Hub aggregation point, Kyengere",
                opens_on=today - timedelta(days=2),
                closes_on=today + timedelta(days=9),
                purchase_limit_kg=120,
                status="open",
            ),
        ]
    )

    # --- one measured trial, so 'measured' beats 'assumed' -----------------
    db.add(
        models.ProductTrial(
            product_key="matooke_flour",
            trial_date=today - timedelta(days=26),
            fresh_input_kg=120.0,
            output_kg=25.4,
            processing_hours=31.0,
            labour_ugx=48000,
            energy_ugx=9000,
            packaging_ugx=21000,
            transport_ugx=14000,
            spoilage_pct=4.5,
            selling_price_ugx_per_kg=5800,
            fresh_price_ugx_per_kg=520,
            notes="Two rainy days extended drying; mill hired at 700 UGX/kg. Batch MS-T-01.",
        )
    )

    # --- opportunities (statuses exercise the expiry/verification rules) ---
    db.add_all(
        [
            models.Opportunity(
                title="Subsidised clean planting material for banana (district pilot)",
                summary=(
                    "District production department is distributing tissue-culture material and "
                    "inspected sword suckers to organised groups, priority to gardens with a "
                    "recorded BXW history."
                ),
                kind="input_support",
                source_name="District Production Department (illustrative notice)",
                source_url="https://www.agriculture.go.ug",
                eligibility="Registered farmer groups in the listed districts; group must have a chairperson and records.",
                how_to_apply=(
                    "Submit the group list and IDs at the parish agricultural office, or hand it to "
                    "the field agent who can upload it. Ask for a receipt with a reference number."
                ),
                districts=["Mukono", "Kayunga", "Luwero"],
                opens_on=today - timedelta(days=10),
                deadline=today + timedelta(days=17),
                verified_on=today - timedelta(days=3),
                verified_by="Field Agent 01",
                is_verified=True,
                status="published",
            ),
            models.Opportunity(
                title="BXW/Sigatoka field days for lead farmers",
                summary="Free practical training on male-bud removal, tool disinfection, de-leafing and record keeping.",
                kind="training",
                source_name="NAADS-type extension programme (illustrative)",
                source_url="https://naads.or.ug",
                eligibility="Open to any farmer; lead farmers get the practical kit.",
                how_to_apply="Tell your parish agricultural development officer or register in the app so we can add your name to the list.",
                districts=None,
                deadline=today + timedelta(days=40),
                verified_on=today - timedelta(days=8),
                verified_by="Field Agent 01",
                is_verified=True,
                status="published",
            ),
            models.Opportunity(
                title="Standards and labelling clinic for processed matooke sellers",
                summary="How to prepare for UNBS marking, what a label must carry, and how to keep batch records.",
                kind="standards",
                source_name="UNBS outreach (illustrative)",
                source_url="https://www.unbs.go.ug",
                eligibility="Groups already producing a packaged food product.",
                how_to_apply="Apply through the UNBS business development desk; bring one sample package.",
                districts=["Kampala", "Wakiso", "Masaka"],
                deadline=today - timedelta(days=5),
                verified_on=today - timedelta(days=70),
                verified_by="Field Agent 01",
                is_verified=True,
                status="published",
            ),
            models.Opportunity(
                title="Grants for agro-processing micro-enterprises",
                summary="Circulated by a WhatsApp broadcast; no official source found yet.",
                kind="grant",
                source_name="Unconfirmed social media post",
                source_url=None,
                eligibility="Unknown - not checked.",
                how_to_apply="Do not pay any 'processing fee'. We will publish the official link if we find one.",
                districts=None,
                deadline=today + timedelta(days=60),
                verified_on=None,
                verified_by=None,
                is_verified=False,
                status="published",
            ),
        ]
    )

    # --- two prior farm-doctor cases ---------------------------------------
    for answers, rating, outcome in (
        (
            {
                "speed": "days",
                "pattern": "one",
                "fruit": "premature",
                "bud": "black",
                "inside": "brown",
                "leaves": "yellow",
            },
            4,
            "Confirmed by the district officer as BXW; mat removed and tools disinfected.",
        ),
        (
            {"speed": "weeks", "leaves": "spots", "conditions": "wet", "pattern": "many"},
            3,
            "Sigatoka confirmed visually; de-leafing scheduled.",
        ),
    ):
        db.add(
            models.DiseaseCase(
                farmer_id=people[0].id,
                farm_id=people[0].farms[0].id,
                answers=answers,
                candidates=[{"key": "see_engine", "name": "resolved by engine at query time"}],
                top_confidence=0.0,
                referred=True,
                farmer_rating=rating,
                expert_outcome=outcome,
            )
        )

    db.commit()
    return {
        "seeded": True,
        "markets": len(markets),
        "people": len(people) + len(buyer_people) + 2,
        "price_records": db.scalar(select(func.count()).select_from(models.PriceRecord)),
        "note": "all prices, yields and costs are synthetic demo values",
    }


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        print(seed(db, force=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
