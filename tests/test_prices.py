"""Price model: honesty of the projection, not just that it runs."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from app.engine.prices import PricePoint, forecast_prices

START = date(2024, 1, 4)


def series(
    days: int = 364,
    step: int = 7,
    base: float = 30000,
    seasonal: dict[int, float] | None = None,
    trend: float = 0.0,
) -> list[PricePoint]:
    seasonal = seasonal or {}
    out = []
    for i in range(0, days, step):
        d = START + timedelta(days=i)
        price = base * (1 + seasonal.get(d.month, 0.0)) * math.exp(trend * i / 30.44)
        out.append(PricePoint(day=d, price_ugx=round(price), verified=True))
    return out


def test_short_history_refuses_to_project():
    fc = forecast_prices([PricePoint(START, 30000), PricePoint(START + timedelta(days=7), 31000)])
    assert fc.confidence == "low"
    assert fc.points == []
    assert any("Too few" in c or "below the minimum" in c for c in fc.caveats)


def test_seasonal_peak_is_priced_above_trough():
    fc = forecast_prices(
        series(seasonal={1: 0.20, 10: -0.20}),
        horizon_days=350,
        step_days=30,
    )
    jan = [p for p in fc.points if p.day.month == 1]
    oct_ = [p for p in fc.points if p.day.month == 10]
    assert fc.confidence in {"high", "medium"}
    assert jan and oct_
    assert jan[0].predicted_ugx > oct_[0].predicted_ugx
    # Seasonal indices keep the sign of the underlying pattern.
    assert fc.seasonal_index["January"] > 0 > fc.seasonal_index["October"]


def test_bands_widen_with_horizon_and_are_ordered():
    fc = forecast_prices(series(seasonal={1: 0.1, 7: -0.1}), horizon_days=120, step_days=14)
    assert len(fc.points) >= 6
    for p in fc.points:
        assert p.low_ugx < p.predicted_ugx < p.high_ugx
    first, last = fc.points[0], fc.points[-1]
    assert (last.high_ugx - last.low_ugx) / last.predicted_ugx > (
        first.high_ugx - first.low_ugx
    ) / first.predicted_ugx


def test_trend_is_clamped_so_few_points_cannot_promise_a_ramp():
    pts = [PricePoint(START + timedelta(days=i * 7), 30000 + i * 4000, verified=True) for i in range(12)]
    fc = forecast_prices(pts, horizon_days=180, step_days=30)
    # 4,000 UGX per week on 30,000 would be ~33 % a month if unclamped.
    assert abs(fc.trend_pct_per_month) <= 12.0


def test_confidence_is_derived_from_backtest_not_asserted():
    """Confidence must fall when the data itself is unforecastable."""
    rng = random.Random(7)
    noisy = [
        PricePoint(
            START + timedelta(days=i * 7),
            int(30000 * rng.uniform(0.72, 1.28)),
            verified=True,
        )
        for i in range(104)
    ]
    smooth = series(728, seasonal={3: 0.12, 9: -0.12})
    fc_noisy = forecast_prices(noisy)
    fc_smooth = forecast_prices(smooth)
    assert fc_smooth.mape_pct is not None
    assert fc_noisy.mape_pct is not None
    assert fc_smooth.mape_pct < fc_noisy.mape_pct
    assert fc_smooth.confidence == "high"
    assert fc_noisy.confidence != "high"


def test_screamingly_noisy_market_downgrades_to_low_and_says_so():
    rng = random.Random(11)
    wild = [
        PricePoint(START + timedelta(days=i * 7), int(30000 * rng.uniform(0.3, 2.1)), verified=True)
        for i in range(104)
    ]
    fc = forecast_prices(wild)
    assert fc.confidence == "low"
    assert any("off by" in c for c in fc.caveats)
    assert any("not a guaranteed" in c.lower() for c in fc.caveats)


def test_summary_never_claims_certainty():
    fc = forecast_prices(series(seasonal={1: 0.1}), horizon_days=60)
    text = fc.summary().lower()
    assert "indicative" in text
    assert "guarantee" not in text
    assert any("not a guaranteed" in c.lower() for c in fc.caveats)


def test_only_two_years_of_weekly_data_yields_about_a_hundred_records():
    fc = forecast_prices(series(728, seasonal={5: -0.1}))
    assert fc.n_records == 104
    assert fc.n_verified == 104
    assert fc.span_days > 700
