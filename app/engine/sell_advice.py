"""5.2 'When to sell' decision support.

The proposal says the output must not be just a chart: it has to answer
"given the expected market conditions, what should I do with my matooke?".
This module turns a `PriceForecast` plus the farmer's own situation into
ranked, priced options - and refuses to recommend waiting when the evidence
behind the forecast is weak.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from .prices import PriceForecast

# Risk discount applied to a forecast-dependent option, by model confidence.
CONFIDENCE_DISCOUNT = {"high": 1.0, "medium": 0.90, "low": 0.72}
# Typical fresh-matooke bunch weight used when converting bunches to kg.
DEFAULT_KG_PER_BUNCH = 27.0
# Illustrative only: what an unsecured short-term cash advance typically costs
# per month, used to frame (not recommend) the pre-order route.
ILLUSTRATIVE_LOAN_RATE_PER_MONTH = 0.10


@dataclass
class Option:
    key: str
    label: str
    detail: str
    expected_revenue_ugx: int
    expected_net_ugx: int
    delta_vs_sell_now_ugx: int
    certainty: str  # "certain now" | "depends on forecast" | "depends on fulfilment"
    risks: list[str] = field(default_factory=list)
    covers_urgent_need: bool | None = None
    cash_now_ugx: int = 0


@dataclass
class SellAdvice:
    headline: str
    primary_option: str
    confidence: str
    price_now_ugx: int | None
    price_at_harvest_ugx: int | None
    expected_change_pct: float | None
    days_to_harvest: int
    quantity_bunches: int
    options: list[Option] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    urgent_need_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _nearest_price(fc: PriceForecast, day: date) -> int | None:
    p = fc.on(day)
    return p.predicted_ugx if p else None


def advise(
    fc: PriceForecast,
    *,
    today: date | None = None,
    harvest_date: date,
    quantity_bunches: int,
    urgent_need_ugx: int = 0,
    can_hold_days: int = 7,
    asking_price_ugx_per_bunch: int | None = None,
    open_requirement_price_ugx: int | None = None,
    hub_buying_note: str | None = None,
    storage_note: str | None = None,
) -> SellAdvice:
    today = today or date.today()
    days_to_harvest = (harvest_date - today).days
    qty = max(int(quantity_bunches), 0)
    price_now = fc.latest_price_ugx or fc.ma28_ugx
    price_at_harvest = _nearest_price(fc, harvest_date) if fc.has_future_projection else None
    discount = CONFIDENCE_DISCOUNT.get(fc.confidence, 0.7)

    a = SellAdvice(
        headline="",
        primary_option="sell_now",
        confidence=fc.confidence,
        price_now_ugx=price_now,
        price_at_harvest_ugx=price_at_harvest,
        expected_change_pct=None,
        days_to_harvest=days_to_harvest,
        quantity_bunches=qty,
        caveats=list(fc.caveats),
    )
    if storage_note:
        a.alerts.append(storage_note)
    if fc.data_is_synthetic:
        a.alerts.append(
            "Price history in this prototype is synthetic sample data, so the numbers below "
            "show how the feature works rather than what your market will do."
        )

    if price_now is None or price_at_harvest is None:
        a.headline = (
            "Not enough reliable price history to tell you whether waiting pays. "
            "Options below are priced from the last recorded market price."
        )
        a.options.append(
            Option(
                key="record_prices",
                label="Record prices, then re-check in a week",
                detail=(
                    "Add 2-3 price observations for your market (date, price per bunch, grade). "
                    "The model needs roughly 40 records before it will project a future price."
                ),
                expected_revenue_ugx=qty * int(price_now or 0),
                expected_net_ugx=qty * int(price_now or 0),
                delta_vs_sell_now_ugx=0,
                certainty="certain now",
            )
        )
        _append_urgent_and_hub(
            a,
            qty=qty,
            price_now=price_now or 0,
            urgent_need_ugx=urgent_need_ugx,
            open_requirement_price_ugx=open_requirement_price_ugx,
            hub_buying_note=hub_buying_note,
            asking_price_ugx_per_bunch=asking_price_ugx_per_bunch,
            harvest_date=harvest_date,
        )
        _finalise(a)
        return a

    change_pct = (price_at_harvest - price_now) / price_now * 100.0
    a.expected_change_pct = round(change_pct, 1)
    sell_now_rev = qty * int(price_now)
    wait_rev = int(qty * price_at_harvest * discount)

    # --- Option: sell fresh now -------------------------------------------
    a.options.append(
        Option(
            key="sell_now",
            label=f"Sell fresh to the market now at about {price_now:,} UGX per bunch",
            detail=(
                f"About {sell_now_rev:,} UGX for {qty:,} bunches at the last recorded price. "
                "Certainty now, no exposure to the forecast."
            ),
            expected_revenue_ugx=sell_now_rev,
            expected_net_ugx=sell_now_rev,
            delta_vs_sell_now_ugx=0,
            certainty="certain now",
            covers_urgent_need=(sell_now_rev >= urgent_need_ugx) if urgent_need_ugx else None,
            cash_now_ugx=sell_now_rev,
        )
    )

    # --- Option: hold / sell at harvest -----------------------------------
    if days_to_harvest <= 0:
        hold_detail = "The harvest is due now, so waiting means holding harvested bunches."
    else:
        hold_detail = (
            f"Leaves the crop standing for {days_to_harvest} more days and sells around "
            f"{harvest_date:%d %b} at an indicative {price_at_harvest:,} UGX per bunch "
            f"({fc.confidence} confidence; range shown in the trend view)."
        )
    a.options.append(
        Option(
            key="wait_to_harvest",
            label=f"Sell at the expected harvest date ({harvest_date:%d %b})",
            detail=hold_detail,
            expected_revenue_ugx=int(qty * price_at_harvest),
            expected_net_ugx=wait_rev,
            delta_vs_sell_now_ugx=wait_rev - sell_now_rev,
            certainty="depends on forecast",
            risks=[
                "Weather, road and labour conditions between now and then",
                "Bunch weight keeps growing but quality and market preference can move",
                "The forecast can be wrong: this model was on average "
                + (
                    f"{fc.mape_pct:.0f} % off in backtesting."
                    if fc.mape_pct
                    else "untested on enough history."
                ),
            ],
            covers_urgent_need=False if urgent_need_ugx else None,
        )
    )

    # --- Option: staged sale ----------------------------------------------
    if qty >= 20:
        half = qty // 2
        staged = int(half * price_now + (qty - half) * price_at_harvest * discount)
        a.options.append(
            Option(
                key="stage",
                label="Split the harvest: sell part now, part later",
                detail=(
                    f"Sell {half} bunches now and {qty - half} around {harvest_date:%d %b}. "
                    "This is the usual hedge when the direction is uncertain."
                ),
                expected_revenue_ugx=int(half * price_now + (qty - half) * price_at_harvest),
                expected_net_ugx=staged,
                delta_vs_sell_now_ugx=staged - sell_now_rev,
                certainty="depends on forecast",
                risks=["Two trips to market, or two buyers to organise"],
                covers_urgent_need=(int(half * price_now) >= urgent_need_ugx) if urgent_need_ugx else None,
                cash_now_ugx=int(half * price_now),
            )
        )

    _append_urgent_and_hub(
        a,
        qty=qty,
        price_now=price_now,
        urgent_need_ugx=urgent_need_ugx,
        open_requirement_price_ugx=open_requirement_price_ugx,
        hub_buying_note=hub_buying_note,
        asking_price_ugx_per_bunch=asking_price_ugx_per_bunch,
        harvest_date=harvest_date,
    )

    # --- Headline rule ----------------------------------------------------
    if fc.confidence == "low":
        a.headline = (
            "The price evidence is too weak to justify waiting. Selling part now and "
            "keeping a small lot is the safer route; do not hold the whole harvest on a guess."
        )
        a.caveats.append(
            "No 'wait for a better price' recommendation is given while forecast confidence is low."
        )
        a.primary_option = "stage" if any(o.key == "stage" for o in a.options) else "sell_now"
    elif change_pct <= -8:
        a.headline = (
            f"The model expects soft prices around your harvest date ({change_pct:.0f} % against "
            "today). Consider selling earlier, pre-ordering the lot at a fixed price, or routing "
            "part of it to value addition rather than the fresh market."
        )
        a.alerts.append(
            "Possible oversupply (glut) window: fresh-market prices are projected below recent levels."
        )
        a.primary_option = "early_order" if urgent_need_ugx else "stage"
    elif change_pct >= 8:
        a.headline = (
            f"Prices are projected about {change_pct:.0f} % firmer near {harvest_date:%d %b}. "
            "If the bunch will hold and you have no urgent cash need, selling then may pay - "
            "but the range is wide and this is not a guarantee."
        )
        a.primary_option = "wait_to_harvest"
    else:
        a.headline = (
            "Prices look broadly flat near your harvest date (within the model's noise). "
            "There is little to gain from timing, so decide on cash need and transport cost."
        )
        a.primary_option = "sell_now"

    _finalise(a)
    return a


def _append_urgent_and_hub(
    a: SellAdvice,
    *,
    qty: int,
    price_now: int,
    urgent_need_ugx: int,
    open_requirement_price_ugx: int | None,
    hub_buying_note: str | None,
    asking_price_ugx_per_bunch: int | None,
    harvest_date: date,
) -> None:
    """Add the early-order and value-addition routes when they are relevant."""
    # A buyer's ceiling is the most they would pay, not the going rate. The price a
    # pre-order can realistically fix is the lower of the market price, what the
    # farmer is asking, and that ceiling - otherwise the model invents free money.
    candidates = [p for p in (price_now, asking_price_ugx_per_bunch, open_requirement_price_ugx) if p]
    ref_price = min(candidates) if candidates else 0
    if ref_price:
        # A buyer locking in future supply typically pays slightly less than a
        # spot buyer takes at the gate, in exchange for certainty on both sides.
        pre_price = round(ref_price * 0.97)
        revenue = qty * pre_price
        a.options.append(
            Option(
                key="early_order",
                label=f"Accept an early order at a fixed {pre_price:,} UGX per bunch",
                detail=(
                    f"Lock {qty} bunches for delivery around {harvest_date:%d %b} at about "
                    f"{pre_price:,} UGX per bunch - a small concession against today's price in "
                    f"exchange for certainty. A deposit (commonly 25 %) is paid before harvest, "
                    f"the balance on delivery: {revenue:,} UGX total."
                ),
                expected_revenue_ugx=revenue,
                expected_net_ugx=revenue,
                delta_vs_sell_now_ugx=revenue - qty * int(price_now or 0),
                certainty="depends on fulfilment",
                risks=[
                    "You must deliver at the agreed quality even if prices rise",
                    "Crop failure must be declared early and handled under the agreed terms",
                    "A buyer can cancel; the deposit terms decide who bears that",
                ],
                covers_urgent_need=(int(revenue * 0.25) >= urgent_need_ugx) if urgent_need_ugx else None,
                cash_now_ugx=int(revenue * 0.25),
            )
        )
    if hub_buying_note:
        a.options.append(
            Option(
                key="value_addition",
                label="Divert part of the lot to processing",
                detail=hub_buying_note,
                expected_revenue_ugx=0,
                expected_net_ugx=0,
                delta_vs_sell_now_ugx=0,
                certainty="depends on fulfilment",
                risks=[
                    "Processing needs drying, milling and packaging capacity",
                    "Check the unit economics before committing a lot",
                ],
            )
        )

    if urgent_need_ugx:
        best_cash = max((o.cash_now_ugx for o in a.options), default=0)
        gap = urgent_need_ugx - best_cash
        monthly = int(urgent_need_ugx * ILLUSTRATIVE_LOAN_RATE_PER_MONTH)
        if gap > 0:
            a.urgent_need_note = (
                f"You indicated an urgent need of {urgent_need_ugx:,} UGX. The best immediate "
                f"cash from these routes is about {best_cash:,} UGX, leaving {gap:,} UGX to cover "
                f"another way. For comparison, {urgent_need_ugx:,} UGX of short-term credit at an "
                f"assumed {ILLUSTRATIVE_LOAN_RATE_PER_MONTH * 100:.0f} % a month costs about "
                f"{monthly:,} UGX each month in interest - shown only as a benchmark, not as an "
                "offer from MatookeSmart."
            )
        else:
            a.urgent_need_note = (
                f"The urgent need of {urgent_need_ugx:,} UGX is covered by immediate cash of about "
                f"{best_cash:,} UGX from the options above, without a credit facility."
            )
        a.alerts.append(
            "Urgent cash need recorded: certainty of getting money now is weighted over chasing a higher price later."
        )


def _finalise(a: SellAdvice) -> None:
    # Never recommend waiting on a weak signal.
    if a.primary_option == "wait_to_harvest" and a.confidence == "low":
        a.primary_option = "stage" if any(o.key == "stage" for o in a.options) else "sell_now"
    scored = [o for o in a.options if o.key != "record_prices"]
    for o in scored:
        if o.key == a.primary_option:
            o.risks.insert(0, "Suggested as the primary route for your inputs")
    a.options.sort(key=lambda o: (o.key != a.primary_option, -o.expected_net_ugx))
