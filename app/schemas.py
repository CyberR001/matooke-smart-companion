"""Request/response models (the API contract)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class FarmerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = None
    district: str | None = None
    language: str = "en"
    tier: str = "basic_farmer"
    consent_profile: bool = False
    consent_images: bool = False
    consent_contact: bool = False


class FarmIn(BaseModel):
    owner_id: int
    name: str
    district: str
    parish: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_acres: float | None = None
    matooke_stands: int | None = None
    hands_per_bunch: float = 17.0
    variety: str = "matooke"
    expected_harvest_date: date | None = None
    notes: str | None = None


class PriceRecordIn(BaseModel):
    market_id: int
    observed_on: date
    price_ugx: int = Field(gt=0)
    quantity_observed: int | None = None
    grade: str = "medium"
    source: str = "field agent"
    verified: bool = False
    notes: str | None = None

    @field_validator("observed_on")
    @classmethod
    def not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("A price observation cannot be dated in the future.")
        return v


class ListingIn(BaseModel):
    seller_id: int
    farm_id: int | None = None
    district: str
    quantity_bunches: int = Field(gt=0)
    hands_per_bunch: float = 17.0
    expected_harvest_date: date
    asking_price_ugx_per_bunch: int = Field(gt=0)
    grade: str = "medium"
    quantity_confidence: str = "medium"
    notes: str | None = None

    @field_validator("quantity_confidence")
    @classmethod
    def check_conf(cls, v: str) -> str:
        if v not in {"low", "medium", "high"}:
            raise ValueError("quantity_confidence must be low, medium or high")
        return v


class RequirementIn(BaseModel):
    buyer_id: int
    organisation: str | None = None
    product: str = "fresh_matooke"
    district: str
    quantity_bunches: int = Field(gt=0)
    needed_by: date
    is_recurring_weekly: bool = False
    min_grade: str = "medium"
    max_price_ugx_per_bunch: int = Field(gt=0)
    willing_deposit_pct: float = Field(default=0.0, ge=0, le=100)
    accepts_future_harvest: bool = True
    notes: str | None = None


class OrderCreateIn(BaseModel):
    listing_id: int
    requirement_id: int
    quantity_bunches: int = Field(gt=0)
    price_per_bunch_ugx: int = Field(gt=0)
    deposit_pct: float = 25.0
    commission_pct: float = 3.0
    delivery_date: date | None = None
    grade: str = "medium"
    cancellation_rule: str | None = None


class OrderActionIn(BaseModel):
    action: str
    actor: str = "system"
    note: str | None = None


class SettleIn(BaseModel):
    delivered_bunches: int = Field(ge=0)
    note: str | None = None


class DoctorAskIn(BaseModel):
    farmer_id: int
    farm_id: int | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    image_provided: bool = False


class SellAdviceIn(BaseModel):
    market_id: int
    harvest_date: date
    quantity_bunches: int = Field(gt=0)
    urgent_need_ugx: int = 0
    can_hold_days: int = 7
    asking_price_ugx_per_bunch: int | None = None
    horizon_days: int = Field(default=60, ge=7, le=180)


class ProcessIn(BaseModel):
    fresh_kg: float = Field(gt=0)
    district: str | None = None
    services: list[str] = Field(default_factory=list)


class TrialIn(BaseModel):
    product_key: str
    fresh_input_kg: float = Field(gt=0)
    output_kg: float = Field(gt=0)
    processing_hours: float | None = None
    labour_ugx: int = 0
    energy_ugx: int = 0
    packaging_ugx: int = 0
    transport_ugx: int = 0
    spoilage_pct: float = 0.0
    selling_price_ugx_per_kg: int = 0
    fresh_price_ugx_per_kg: int = 0
    notes: str | None = None
    trial_date: date | None = None


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    note: str | None = None
