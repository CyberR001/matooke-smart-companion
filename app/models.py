"""Domain model for the MatookeSmart Companion prototype.

Tables are grouped by the module they serve (concept proposal section 5):

  5.1 farm doctor      DiseaseCase
  5.2 market intel     Market, PriceRecord, ForecastRun
  5.3 surplus/products ProductTrial
  5.4 early orders     HarvestListing, BuyerRequirement, EarlyOrder, OrderEvent
  5.5 marketplace      ListingStatus / MatchRun, HubBuyingNotice
  5.6 opportunities    Opportunity
  5.7 membership       Person, Farm, Subscription
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# --------------------------------------------------------------------------
# 5.7 Membership and profiles
# --------------------------------------------------------------------------

TIERS = ("basic_farmer", "smart_farmer", "professional_farmer", "buyer_institution")
ROLES = ("farmer", "buyer", "hub", "staff")


class Person(Base):
    """Farmer, institutional buyer, Hub staff or field agent."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="farmer")
    district: Mapped[str | None] = mapped_column(String(60), index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    tier: Mapped[str] = mapped_column(String(32), default="basic_farmer")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Data Protection and Privacy Act 2019 - record the consent we obtained.
    consent_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_images: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_contact: Mapped[bool] = mapped_column(Boolean, default=False)

    farms: Mapped[list[Farm]] = relationship(back_populates="owner")
    listings: Mapped[list[HarvestListing]] = relationship(back_populates="seller")
    requirements: Mapped[list[BuyerRequirement]] = relationship(back_populates="buyer")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="person")


class Farm(Base):
    __tablename__ = "farm"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    district: Mapped[str] = mapped_column(String(60), index=True)
    parish: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    area_acres: Mapped[float | None] = mapped_column(Float)
    planting_date: Mapped[date | None] = mapped_column(Date)
    expected_harvest_date: Mapped[date | None] = mapped_column(Date)
    matooke_stands: Mapped[int | None] = mapped_column(Integer)
    hands_per_bunch: Mapped[float | None] = mapped_column(Float, default=17.0)
    variety: Mapped[str] = mapped_column(String(40), default="matooke")
    notes: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[Person] = relationship(back_populates="farms")
    cases: Mapped[list[DiseaseCase]] = relationship(back_populates="farm")
    listings: Mapped[list[HarvestListing]] = relationship(back_populates="farm_ref")


class Subscription(Base):
    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    tier: Mapped[str] = mapped_column(String(32))
    amount_ugx: Mapped[int] = mapped_column(Integer, default=0)
    # Prices are validation hypotheses (section 5.7), never confirmed tariffs.
    price_is_hypothesis: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    started_on: Mapped[date] = mapped_column(Date, default=date.today)
    expires_on: Mapped[date | None] = mapped_column(Date)

    person: Mapped[Person] = relationship(back_populates="subscriptions")


# --------------------------------------------------------------------------
# 5.2 Market intelligence
# --------------------------------------------------------------------------


class Market(Base):
    __tablename__ = "market"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    district: Mapped[str] = mapped_column(String(60), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32), default="bunch")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    prices: Mapped[list[PriceRecord]] = relationship(back_populates="market")


class PriceRecord(Base):
    """One observed price at one market on one date (section 7 data contract).

    `source` and `verified` are mandatory in spirit: the UI must show where a
    number came from and whether a human confirmed it.
    """

    __tablename__ = "price_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"), index=True)
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    price_ugx: Mapped[int] = mapped_column(Integer)
    quantity_observed: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(16), default="medium")
    source: Mapped[str] = mapped_column(String(120), default="field agent")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    collector_id: Mapped[int | None] = mapped_column(ForeignKey("person.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    market: Mapped[Market] = relationship(back_populates="prices")


class ForecastRun(Base):
    """Stored so we can audit and later grade our own accuracy."""

    __tablename__ = "forecast_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("market.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    horizon_days: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(60))
    mape_pct: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict | None] = mapped_column(JSON)


# --------------------------------------------------------------------------
# 5.1 Farm doctor
# --------------------------------------------------------------------------


class DiseaseCase(Base):
    __tablename__ = "disease_case"

    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey("farm.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    image_path: Mapped[str | None] = mapped_column(String(255))
    answers: Mapped[dict | None] = mapped_column(JSON)
    candidates: Mapped[list | None] = mapped_column(JSON)
    top_confidence: Mapped[float | None] = mapped_column(Float)
    referred: Mapped[bool] = mapped_column(Boolean, default=False)
    farmer_rating: Mapped[int | None] = mapped_column(Integer)  # 1-5 usefulness
    expert_outcome: Mapped[str | None] = mapped_column(String(80))

    farm: Mapped[Farm | None] = relationship(back_populates="cases")


# --------------------------------------------------------------------------
# 5.3 Surplus and value addition
# --------------------------------------------------------------------------


class ProductTrial(Base):
    """One measured processing trial (section 5.3: measure before claiming).

    A trial replaces the catalog assumption for a product and is labelled with
    its provenance so profitability claims stay traceable.
    """

    __tablename__ = "product_trial"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(40), index=True)
    trial_date: Mapped[date] = mapped_column(Date, default=date.today)
    fresh_input_kg: Mapped[float] = mapped_column(Float)
    output_kg: Mapped[float] = mapped_column(Float)
    processing_hours: Mapped[float | None] = mapped_column(Float)
    labour_ugx: Mapped[int] = mapped_column(Integer, default=0)
    energy_ugx: Mapped[int] = mapped_column(Integer, default=0)
    packaging_ugx: Mapped[int] = mapped_column(Integer, default=0)
    transport_ugx: Mapped[int] = mapped_column(Integer, default=0)
    spoilage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    selling_price_ugx_per_kg: Mapped[int] = mapped_column(Integer, default=0)
    fresh_price_ugx_per_kg: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class HubBuyingNotice(Base):
    """What the MatookeSmart Hub is currently buying, and on what terms."""

    __tablename__ = "hub_buying_notice"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    accepts: Mapped[str] = mapped_column(String(40))  # product_key or "fresh_matooke"
    accepts_form: Mapped[str] = mapped_column(String(40), default="fresh surplus")
    quality_spec: Mapped[str] = mapped_column(Text)
    quantity_kg: Mapped[int] = mapped_column(Integer, default=0)
    price_basis: Mapped[str] = mapped_column(String(80), default="UGX per kg")
    price_ugx_per_unit: Mapped[int] = mapped_column(Integer, default=0)
    district: Mapped[str] = mapped_column(String(60), default="Kampala")
    pickup_point: Mapped[str | None] = mapped_column(String(120))
    opens_on: Mapped[date] = mapped_column(Date, default=date.today)
    closes_on: Mapped[date | None] = mapped_column(Date)
    purchase_limit_kg: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="open")

    @property
    def is_live(self) -> bool:
        today = date.today()
        return (
            self.status == "open"
            and self.opens_on <= today
            and (self.closes_on is None or self.closes_on >= today)
        )


# --------------------------------------------------------------------------
# 5.4 / 5.5 Early orders and marketplace
# --------------------------------------------------------------------------

ORDER_STATUSES = (
    "proposed",
    "terms_sent",
    "awaiting_deposit",
    "confirmed",
    "in_growth",
    "ready_for_delivery",
    "delivered",
    "settled",
    "cancelled",
    "disputed",
)


class HarvestListing(Base):
    """A farmer's advertised future (or standing) harvest."""

    __tablename__ = "harvest_listing"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey("farm.id"))
    district: Mapped[str] = mapped_column(String(60), index=True)
    quantity_bunches: Mapped[int] = mapped_column(Integer)
    hands_per_bunch: Mapped[float] = mapped_column(Float, default=17.0)
    expected_harvest_date: Mapped[date] = mapped_column(Date, index=True)
    quantity_confidence: Mapped[str] = mapped_column(String(16), default="medium")
    grade: Mapped[str] = mapped_column(String(16), default="medium")
    asking_price_ugx_per_bunch: Mapped[int] = mapped_column(Integer)
    committed_bunches: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    seller: Mapped[Person] = relationship(back_populates="listings")
    farm_ref: Mapped[Farm | None] = relationship(back_populates="listings")


class BuyerRequirement(Base):
    """What a buyer needs, now or in future."""

    __tablename__ = "buyer_requirement"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("person.id"), index=True)
    organisation: Mapped[str | None] = mapped_column(String(120))
    product: Mapped[str] = mapped_column(String(40), default="fresh_matooke")
    district: Mapped[str] = mapped_column(String(60), index=True)
    quantity_bunches: Mapped[int] = mapped_column(Integer)
    needed_by: Mapped[date] = mapped_column(Date)
    is_recurring_weekly: Mapped[bool] = mapped_column(Boolean, default=False)
    min_grade: Mapped[str] = mapped_column(String(16), default="medium")
    max_price_ugx_per_bunch: Mapped[int] = mapped_column(Integer)
    willing_deposit_pct: Mapped[float] = mapped_column(Float, default=0.0)
    accepts_future_harvest: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    buyer: Mapped[Person] = relationship(back_populates="requirements")


class EarlyOrder(Base):
    """Advance-purchase agreement between one listing and one requirement.

    Deliberately records *commercial* terms (deposit, cancellation, force
    majeure) because this is a pre-order, not a loan (Appendix A).
    """

    __tablename__ = "early_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("harvest_listing.id"))
    requirement_id: Mapped[int] = mapped_column(ForeignKey("buyer_requirement.id"))
    quantity_bunches: Mapped[int] = mapped_column(Integer)
    agreed_price_ugx_per_bunch: Mapped[int] = mapped_column(Integer)
    deposit_pct: Mapped[float] = mapped_column(Float, default=25.0)
    advance_paid_ugx: Mapped[int] = mapped_column(Integer, default=0)
    balance_due_ugx: Mapped[int] = mapped_column(Integer, default=0)
    commission_pct: Mapped[float] = mapped_column(Float, default=3.0)
    service_fee_ugx: Mapped[int] = mapped_column(Integer, default=0)
    delivery_date: Mapped[date] = mapped_column(Date)
    grade: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    cancellation_rule: Mapped[str] = mapped_column(
        String(240),
        default=(
            "Either party may cancel before the deposit is paid. After a deposit, "
            "cancellation by the buyer forfeits the deposit; cancellation by the "
            "farmer for reasons other than documented crop failure repays the "
            "deposit. Crop failure triggers rescheduling, not automatic repayment "
            "demands."
        ),
    )
    crop_failure_declared: Mapped[bool] = mapped_column(Boolean, default=False)
    terms_snapshot: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    listing: Mapped[HarvestListing] = relationship()
    requirement: Mapped[BuyerRequirement] = relationship()
    events: Mapped[list[OrderEvent]] = relationship(back_populates="order", order_by="OrderEvent.id")


class OrderEvent(Base):
    """Audit trail; disputes are resolved from this, not from memory."""

    __tablename__ = "order_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("early_order.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor: Mapped[str] = mapped_column(String(60), default="system")
    kind: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)

    order: Mapped[EarlyOrder] = relationship(back_populates="events")


class MatchRun(Base):
    """A stored matching suggestion, so we can measure take-up (section 10)."""

    __tablename__ = "match_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    listing_id: Mapped[int] = mapped_column(ForeignKey("harvest_listing.id"))
    requirement_id: Mapped[int] = mapped_column(ForeignKey("buyer_requirement.id"))
    score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict | None] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(24), default="suggested")


# --------------------------------------------------------------------------
# 5.6 Opportunities and alerts
# --------------------------------------------------------------------------


class Opportunity(Base):
    __tablename__ = "opportunity"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), default="input_support")
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(300))
    eligibility: Mapped[str | None] = mapped_column(Text)
    how_to_apply: Mapped[str | None] = mapped_column(Text)
    districts: Mapped[list | None] = mapped_column(JSON)  # None => nationwide
    opens_on: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    verified_on: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(80))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    requires_unbs: Mapped[bool] = mapped_column(Boolean, default=False)
