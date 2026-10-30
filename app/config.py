"""Runtime configuration.

Environment-driven so the same code runs on SQLite for a demo/field pilot and
on PostgreSQL in production, per section 7 of the concept proposal.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MatookeSmart Companion"
    tagline: str = "Your matooke. Better decisions. Better markets."

    # SQLite by default; set DATABASE_URL=postgresql+psycopg://... for Postgres.
    database_url: str = "sqlite:///./data/matookesmart.db"

    # --- Responsible-AI thresholds (sections 5.1, 5.2, 12) ---
    # A candidate condition below this confidence is never shown as an answer;
    # the case is referred to a person instead.
    disease_referral_confidence: float = 0.45
    # Forecasts below this confidence carry an explicit "do not rely on this"
    # banner and no "wait" recommendation.
    forecast_low_confidence_mape: float = 0.20
    forecast_high_confidence_mape: float = 0.10
    min_records_for_forecast: int = 40

    # --- Commercial defaults (hypotheses, not prices - section 5.7/8) ---
    default_commission_pct: float = 3.0
    default_deposit_pct: float = 25.0
    # Required fresh-weight margin before the app calls a product "worthwhile".
    min_attractive_margin_pct: float = 15.0

    seed_demo_data: bool = True

    # --- Deployment ---
    environment: str = "development"
    # Comma-separated origins allowed to call the API from a browser (empty = none).
    cors_origins: str = ""
    # Writes per client per minute; 0 disables the limiter.
    rate_limit_per_min: int = 120
    # App default behaviour: no synthetic-data banner in the UI. Keep this empty
    # unless you deliberately want a visible prototype warning.
    data_disclaimer: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
