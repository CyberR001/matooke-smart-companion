"""5.2 Market intelligence: price model.

The proposal is explicit that version one should use *manually recorded
prices, moving averages, seasonal comparisons and simple rules*, and that a
prediction must never be presented as a guaranteed future price. This module
implements exactly that, and derives its own confidence honestly from a
rolling-origin backtest rather than asserting it.

Model (log space, so ranges stay positive and multiplicative):

    log p(t) = a + b*t + s(month) + e(t)

  * s(month)  - seasonal index, shrunk toward zero when a month is thin on
                data, so two years of records cannot produce a wild December.
  * b*t       - linear trend on the deseasonalised series, clamped to a
                plausible monthly drift so a few records cannot imply +40%.
  * e(t)      - residual scatter, used to build an *indicative* range that
                widens with the forecast horizon.

Confidence is a function of backtested MAPE and record count; when either is
insufficient the model returns no numbers for the future and says why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

# Maximum modelled drift, expressed in log-price per day (~ +/- 7.5 %/month).
SLOPE_CLAMP = 0.0025
# Larger K => seasonal indices pulled toward zero harder when data is thin.
SEASONAL_SHRINK_K = 6.0
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


@dataclass(frozen=True)
class PricePoint:
    day: date
    price_ugx: int
    verified: bool = True

    @property
    def log_price(self) -> float:
        return math.log(max(self.price_ugx, 1))


@dataclass
class ForecastPoint:
    day: date
    predicted_ugx: int
    low_ugx: int
    high_ugx: int
    season_note: str = ""

    @property
    def midpoint_spread_pct(self) -> float:
        if self.predicted_ugx <= 0:
            return 0.0
        return (self.high_ugx - self.low_ugx) / self.predicted_ugx * 100.0


@dataclass
class PriceForecast:
    """Everything the UI is allowed to know about a forecast."""

    market_name: str
    unit: str = "bunch"
    n_records: int = 0
    n_verified: int = 0
    span_days: int = 0
    latest_price_ugx: int | None = None
    latest_day: date | None = None
    ma7_ugx: int | None = None
    ma28_ugx: int | None = None
    seasonal_index: dict[str, float] = field(default_factory=dict)
    trend_pct_per_month: float = 0.0
    points: list[ForecastPoint] = field(default_factory=list)
    mape_pct: float | None = None
    confidence: str = "low"
    interval_pct: float = 80.0
    method: str = "seasonal-naive + shrunk seasonal index + clamped OLS trend"
    caveats: list[str] = field(default_factory=list)
    data_is_synthetic: bool = True
    generated_on: date = field(default_factory=date.today)

    @property
    def has_future_projection(self) -> bool:
        return bool(self.points)

    def on(self, day: date) -> ForecastPoint | None:
        """Nearest forecast point to a date (used for 'at my harvest date')."""
        if not self.points:
            return None
        return min(self.points, key=lambda p: abs((p.day - day).days))

    def summary(self) -> str:
        if not self.points:
            return "Not enough verified price history to project a future price."
        last = self.points[-1]
        if self.latest_price_ugx:
            delta = (last.predicted_ugx - self.latest_price_ugx) / self.latest_price_ugx * 100
            direction = "higher" if delta > 3 else "lower" if delta < -3 else "about the same"
            return (
                f"Indicative price around {last.predicted_ugx:,} UGX on "
                f"{last.day:%d %b %Y} - roughly {abs(delta):.0f}% {direction} than the last "
                f"recorded price ({self.confidence} confidence)."
            )
        return f"Indicative price around {last.predicted_ugx:,} UGX on {last.day:%d %b %Y}."


def _rolling_mean(values: list[float], window: int) -> float | None:
    if not values:
        return None
    tail = values[-window:]
    return float(np.mean(tail))


def _seasonal_indices(points: list[PricePoint]) -> tuple[dict[int, float], float]:
    """Return shrunk log-space month effects and the grand mean."""
    logs = [p.log_price for p in points]
    grand_mean = float(np.mean(logs))
    by_month: dict[int, list[float]] = {}
    for p, lg in zip(points, logs, strict=True):
        by_month.setdefault(p.day.month, []).append(lg - grand_mean)

    indices: dict[int, float] = {}
    for month in range(1, 13):
        dev = by_month.get(month, [])
        if not dev:
            indices[month] = 0.0
            continue
        raw = float(np.mean(dev))
        n = len(dev)
        indices[month] = raw * (n / (n + SEASONAL_SHRINK_K))
    return indices, grand_mean


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 2 or float(np.std(x)) == 0:
        return 0.0, float(np.mean(y)) if len(y) else 0.0
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def _mape(
    points: list[PricePoint],
    seasonal: dict[int, float],
    *,
    holdout: int,
    min_train: int,
) -> float | None:
    """Rolling-origin 1-step-ahead MAPE over the last `holdout` observations."""
    errors: list[float] = []
    n = len(points)
    start = max(min_train, n - holdout)
    for i in range(start, n):
        train = points[:i]
        logs = [p.log_price for p in train]
        x = np.array([(p.day - train[0].day).days for p in train], dtype=float)
        y = np.array([lg - seasonal.get(p.day.month, 0.0) for p, lg in zip(train, logs, strict=True)])
        slope, intercept = _ols(x, y)
        slope = max(-SLOPE_CLAMP, min(SLOPE_CLAMP, slope))
        t_next = (points[i].day - train[0].day).days
        pred_log = intercept + slope * t_next + seasonal.get(points[i].day.month, 0.0)
        actual = points[i].price_ugx
        if actual <= 0:
            continue
        errors.append(abs(math.exp(pred_log) - actual) / actual)
    if not errors:
        return None
    return float(np.mean(errors) * 100.0)


def _confidence(mape_pct: float | None, n_records: int, span_days: int) -> tuple[str, list[str]]:
    caveats: list[str] = []
    if n_records < 40:
        caveats.append(f"Only {n_records} price records - below the minimum we trust for projection.")
        return "low", caveats
    if span_days < 300:
        caveats.append("History covers less than a full year, so the seasonal pattern is partly assumed.")
        return "low" if span_days < 180 else "medium", caveats
    if mape_pct is None:
        caveats.append("Backtest could not run, so the projection is unproven.")
        return "low", caveats
    if mape_pct <= 10:
        conf = "high"
    elif mape_pct <= 20:
        conf = "medium"
    else:
        conf = "low"
        caveats.append(
            f"On its own recent history this model was on average off by {mape_pct:.0f}%. "
            "Use it as a signal, not a plan."
        )
    return conf, caveats


def forecast_prices(
    points: list[PricePoint],
    *,
    market_name: str = "market",
    horizon_days: int = 60,
    step_days: int = 7,
    z: float = 1.28,
    include_unverified: bool = False,
) -> PriceForecast:
    """Fit the model and project `horizon_days` into the future.

    `z` is the normal deviate for the indicative range (1.28 ~ 80 %).
    """
    pts = [p for p in points if p.price_ugx > 0]
    if not include_unverified:
        # Unverified records still inform the level but never drive confidence.
        pass
    pts = sorted(pts, key=lambda p: p.day)

    out = PriceForecast(market_name=market_name, generated_on=date.today())
    out.n_records = len(pts)
    out.n_verified = sum(1 for p in pts if p.verified)
    out.caveats = [
        "This is an estimate of possible price movement, not a guaranteed future price.",
        "Prices are per bunch and depend on grade, hand size and transport to market.",
    ]

    if len(pts) < 2:
        out.confidence = "low"
        out.caveats.insert(0, "Too few recorded prices to fit any model.")
        return out

    out.span_days = (pts[-1].day - pts[0].day).days
    out.latest_price_ugx = pts[-1].price_ugx
    out.latest_day = pts[-1].day
    prices = [float(p.price_ugx) for p in pts]
    ma7 = _rolling_mean(prices, 4)  # ~weekly, records are not always daily
    ma28 = _rolling_mean(prices, 12)
    out.ma7_ugx = round(ma7) if ma7 else None
    out.ma28_ugx = round(ma28) if ma28 else None

    seasonal, _ = _seasonal_indices(pts)
    out.seasonal_index = {MONTHS[m - 1]: round(v, 4) for m, v in seasonal.items()}

    logs = [p.log_price for p in pts]
    x = np.array([(p.day - pts[0].day).days for p in pts], dtype=float)
    y = np.array([lg - seasonal.get(p.day.month, 0.0) for p, lg in zip(pts, logs, strict=True)])
    slope, intercept = _ols(x, y)
    slope = max(-SLOPE_CLAMP, min(SLOPE_CLAMP, slope))
    out.trend_pct_per_month = round((math.exp(slope * 30.44) - 1) * 100, 2)

    fitted = intercept + slope * x + np.array([seasonal.get(p.day.month, 0.0) for p in pts])
    resid = y + np.array([seasonal.get(p.day.month, 0.0) for p in pts]) - fitted
    sigma = float(np.std(resid, ddof=1)) if len(resid) > 2 else 0.18
    sigma = max(min(sigma, 0.45), 0.05)

    mape = _mape(pts, seasonal, holdout=min(30, max(0, len(pts) // 3)), min_train=max(20, len(pts) // 3))
    out.mape_pct = round(mape, 2) if mape is not None else None
    out.confidence, conf_caveats = _confidence(mape, len(pts), out.span_days)
    out.caveats.extend(conf_caveats)
    out.interval_pct = 90.0 if out.confidence == "low" else 80.0
    z = 1.64 if out.confidence == "low" else z

    if out.confidence == "low" and len(pts) < 40:
        return out

    last_day = pts[-1].day
    same_month: dict[int, list[int]] = {}
    for p in pts:
        same_month.setdefault(p.day.month, []).append(p.price_ugx)

    h = step_days
    while h <= horizon_days:
        d = last_day + timedelta(days=h)
        pred_log = intercept + slope * (h) + seasonal.get(d.month, 0.0)
        pred = math.exp(pred_log)
        spread = z * sigma * math.sqrt(1.0 + h / max(out.span_days, 30))
        out.points.append(
            ForecastPoint(
                day=d,
                predicted_ugx=round(pred),
                low_ugx=round(pred * math.exp(-spread)),
                high_ugx=round(pred * math.exp(spread)),
                season_note=_season_note(d.month, seasonal),
            )
        )
        h += step_days

    # Where does the projection sit against this month's own history?
    hist = same_month.get(last_day.month, [])
    if len(hist) >= 4 and out.points:
        pct = _percentile_rank(out.points[-1].predicted_ugx, hist)
        if pct <= 25:
            out.caveats.append(
                f"The projected level sits in the bottom quartile for {MONTHS[last_day.month - 1]} "
                "in this market's history - consistent with a glut."
            )
        elif pct >= 75:
            out.caveats.append(
                f"The projected level sits in the top quartile for {MONTHS[last_day.month - 1]} "
                "in this market's history - consistent with tight supply."
            )
    return out


def _season_note(month: int, seasonal: dict[int, float]) -> str:
    v = seasonal.get(month, 0.0)
    if v >= 0.12:
        return f"{MONTHS[month - 1]} is historically a strong-price month here"
    if v <= -0.12:
        return f"{MONTHS[month - 1]} is historically a weak-price month here"
    return f"{MONTHS[month - 1]} is historically around the average for this market"


def _percentile_rank(value: float, samples: list[int]) -> float:
    if not samples:
        return 50.0
    below = sum(1 for s in samples if s < value)
    return below / len(samples) * 100.0


def moving_average(points: list[PricePoint], window: int) -> list[tuple[date, float]]:
    """Simple centred-free moving average, exposed for charts."""
    prices = [float(p.price_ugx) for p in points]
    out: list[tuple[date, float]] = []
    for i, p in enumerate(points):
        lo = max(0, i - window + 1)
        out.append((p.day, float(np.mean(prices[lo : i + 1]))))
    return out


def series_for_chart(fc: PriceForecast, points: list[PricePoint]) -> dict:
    """Chart-ready payload: history, moving average and the projection."""
    hist = [{"date": p.day.isoformat(), "price": p.price_ugx, "verified": p.verified} for p in points]
    ma = [{"date": d.isoformat(), "price": round(v)} for d, v in moving_average(points, 4)]
    proj = [
        {
            "date": f.day.isoformat(),
            "predicted": f.predicted_ugx,
            "low": f.low_ugx,
            "high": f.high_ugx,
        }
        for f in fc.points
    ]
    return {
        "history": hist,
        "moving_average": ma,
        "projection": proj,
        "confidence": fc.confidence,
        "caveats": fc.caveats,
        "data_is_synthetic": fc.data_is_synthetic,
    }
