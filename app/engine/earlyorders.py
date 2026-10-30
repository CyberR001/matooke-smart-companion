"""5.4 Early orders: the advance-purchase agreement.

The proposal is careful about the distinction that must survive in the code:
this is a **commercial pre-order**, not a loan. So the engine

  * computes money from an agreed price and quantity (no interest anywhere),
  * records terms, deposit and balance, and an event trail for disputes,
  * treats crop failure as a rescheduling/partial-delivery path rather than a
    demand for immediate repayment,
  * never claims to hold funds: payment custody is described as a partner
    flow because that is what section 13 requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MAX_DEPOSIT_PCT = 60.0
MIN_DEPOSIT_PCT = 0.0

# Legal forward order of states; anything else is rejected with a reason.
TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"terms_sent", "cancelled"},
    "terms_sent": {"awaiting_deposit", "proposed", "cancelled"},
    "awaiting_deposit": {"confirmed", "cancelled", "disputed"},
    "confirmed": {"in_growth", "cancelled", "disputed"},
    "in_growth": {"ready_for_delivery", "disputed", "cancelled"},
    "ready_for_delivery": {"delivered", "disputed"},
    "delivered": {"settled", "disputed"},
    "settled": set(),
    "cancelled": set(),
    "disputed": {"cancelled", "settled", "delivered"},
}

ACTION_LABELS = {
    "propose": "proposed",
    "send_terms": "terms_sent",
    "request_deposit": "awaiting_deposit",
    "confirm": "confirmed",
    "start_growth": "in_growth",
    "mark_ready": "ready_for_delivery",
    "deliver": "delivered",
    "settle": "settled",
    "cancel": "cancelled",
    "raise_dispute": "disputed",
}

ACTION_FROM: dict[str, set[str]] = {
    "send_terms": {"proposed"},
    "request_deposit": {"terms_sent"},
    "confirm": {"awaiting_deposit", "terms_sent"},
    "start_growth": {"confirmed"},
    "mark_ready": {"in_growth"},
    "deliver": {"ready_for_delivery", "in_growth"},
    "settle": {"delivered"},
    "cancel": {"proposed", "terms_sent", "awaiting_deposit", "confirmed", "in_growth"},
    "raise_dispute": {"awaiting_deposit", "confirmed", "in_growth", "ready_for_delivery", "delivered"},
}


class InvalidTransition(ValueError):
    """Raised when a status change is not allowed by the order lifecycle."""


@dataclass
class OrderTerms:
    quantity_bunches: int
    price_per_bunch_ugx: int
    deposit_pct: float
    commission_pct: float

    @property
    def total_value_ugx(self) -> int:
        return self.quantity_bunches * self.price_per_bunch_ugx

    @property
    def advance_ugx(self) -> int:
        return round(self.total_value_ugx * self.deposit_pct / 100.0)

    @property
    def balance_ugx(self) -> int:
        return self.total_value_ugx - self.advance_ugx

    @property
    def service_fee_ugx(self) -> int:
        return round(self.total_value_ugx * self.commission_pct / 100.0)

    @property
    def farmer_net_ugx(self) -> int:
        """What the farmer keeps after the disclosed platform fee."""
        return self.total_value_ugx - self.service_fee_ugx


def normalise_terms(
    *,
    quantity_bunches: int,
    price_per_bunch_ugx: int,
    deposit_pct: float,
    commission_pct: float,
) -> tuple[OrderTerms, list[str]]:
    """Clamp to sane bounds and say what was changed (no silent edits)."""
    notes: list[str] = []
    qty = max(int(quantity_bunches), 1)
    price = max(int(price_per_bunch_ugx), 1)
    dep = float(deposit_pct)
    if dep < MIN_DEPOSIT_PCT:
        notes.append(f"Deposit of {dep:.0f} % is not usable; set to {MIN_DEPOSIT_PCT:.0f} %.")
        dep = MIN_DEPOSIT_PCT
    if dep > MAX_DEPOSIT_PCT:
        notes.append(
            f"Deposit capped at {MAX_DEPOSIT_PCT:.0f} %. Asking a buyer for more up front "
            "shifts all the risk to them and needs a custody arrangement we do not offer."
        )
        dep = MAX_DEPOSIT_PCT
    comm = float(max(min(commission_pct, 15.0), 0.0))
    if commission_pct > 15.0:
        notes.append("Commission capped at 15 % for the prototype; disclose any fee change in advance.")
    return OrderTerms(qty, price, round(dep, 1), round(comm, 1)), notes


def build_order(
    *,
    reference: str,
    listing_id: int,
    requirement_id: int,
    terms: OrderTerms,
    delivery_date: date,
    grade: str = "medium",
    harvest_estimate_confidence: str = "medium",
    cancellation_rule: str | None = None,
    today: date | None = None,
) -> dict:
    """Create the order payload including the terms snapshot both parties see."""
    today = today or date.today()
    if delivery_date < today:
        raise ValueError("Delivery date is in the past; agree a realistic date before posting.")
    if (delivery_date - today).days < 3 and harvest_estimate_confidence != "high":
        raise ValueError(
            "Delivery is inside 3 days. Post it as an immediate marketplace sale instead of "
            "an early order, or confirm the lot is already harvested."
        )
    warn: list[str] = []
    if harvest_estimate_confidence == "low":
        warn.append(
            "Harvest estimate marked unreliable: keep the quantity below what you are confident "
            "about, because short delivery is the most common dispute in this model."
        )
    if (delivery_date - today).days < 14:
        warn.append("Short lead time: the buyer has little protection if anything goes wrong.")

    return {
        "reference": reference,
        "listing_id": listing_id,
        "requirement_id": requirement_id,
        "quantity_bunches": terms.quantity_bunches,
        "agreed_price_ugx_per_bunch": terms.price_per_bunch_ugx,
        "deposit_pct": terms.deposit_pct,
        "advance_paid_ugx": 0,
        "balance_due_ugx": terms.balance_ugx,
        "commission_pct": terms.commission_pct,
        "service_fee_ugx": terms.service_fee_ugx,
        "delivery_date": delivery_date,
        "grade": grade,
        "status": "proposed",
        "cancellation_rule": cancellation_rule or DEFAULT_CANCELLATION_RULE,
        "crop_failure_declared": False,
        "terms_snapshot": {
            "total_value_ugx": terms.total_value_ugx,
            "advance_ugx": terms.advance_ugx,
            "balance_ugx": terms.balance_ugx,
            "service_fee_ugx": terms.service_fee_ugx,
            "farmer_net_ugx": terms.farmer_net_ugx,
            "price_per_hand_ugx": round(terms.price_per_bunch_ugx / 17.0, 1),
            "payment_note": (
                "Advance and balance are agreed between buyer and farmer and moved through an "
                "authorised payment partner. MatookeSmart records the order; it does not hold "
                "the money and this is not a loan."
            ),
            "warnings": warn,
        },
    }


DEFAULT_CANCELLATION_RULE = (
    "Either party may cancel before a deposit is paid. After a deposit: a buyer who "
    "cancels without cause forfeits the deposit; a farmer who cancels without cause "
    "repays it in full. Documented crop failure (extension-verified where possible) "
    "leads to rescheduling or partial supply, not an immediate repayment demand."
)


def transition(status: str, action: str) -> tuple[str, str]:
    """Return (new_status, message). Raises InvalidTransition when not allowed."""
    if action not in ACTION_LABELS:
        raise InvalidTransition(f"Unknown action '{action}'.")
    allowed = ACTION_FROM.get(action, set())
    target = ACTION_LABELS[action]
    if status not in allowed and target not in TRANSITIONS.get(status, set()):
        raise InvalidTransition(
            f"Cannot go from '{status}' to '{target}' via '{action}'. "
            f"Allowed next steps: {sorted(TRANSITIONS.get(status, set())) or 'none (closed order)'}."
        )
    if action == "settle" and status != "delivered":
        raise InvalidTransition("Settlement is only recorded after delivery.")
    return target, f"Order moved to {target.replace('_', ' ')}."


def settle(
    terms: OrderTerms,
    *,
    delivered_bunches: int,
    advance_paid_ugx: int,
    agreed_price_ugx_per_bunch: int | None = None,
) -> dict:
    """Final money movement, including short delivery.

    Three separate numbers, because conflating them is how disputes start:

      * what the **buyer** still owes   = value delivered - advance already paid
      * what the **farmer** keeps       = value delivered - platform fee
      * what the **platform** earns     = the fee, netted out of the balance

    Short delivery is priced at the agreed rate for what was actually supplied,
    so the farmer is not penalised twice and the buyer does not overpay.
    """
    price = agreed_price_ugx_per_bunch or terms.price_per_bunch_ugx
    delivered = max(int(delivered_bunches), 0)
    supplied_value = delivered * price
    fee = round(supplied_value * terms.commission_pct / 100.0)
    farmer_total = supplied_value - fee

    buyer_balance = supplied_value - advance_paid_ugx
    refund_due = -buyer_balance if buyer_balance < 0 else 0
    buyer_balance = max(buyer_balance, 0)
    to_farmer_now = buyer_balance - fee
    fee_netted = to_farmer_now >= 0
    if not fee_netted:
        # Nothing to net the fee from: the fee stays owed under the agreed terms.
        to_farmer_now = 0

    shortfall = max(terms.quantity_bunches - delivered, 0)
    lines = [
        f"Delivered {delivered} of {terms.quantity_bunches} bunches at {price:,} UGX.",
        f"Value of delivered produce: {supplied_value:,} UGX.",
        f"Advance already paid to the farmer: {advance_paid_ugx:,} UGX.",
        f"Platform service fee ({terms.commission_pct:g} %): {fee:,} UGX.",
        f"Buyer still owes: {buyer_balance:,} UGX.",
        f"Of that, {to_farmer_now:,} UGX goes to the farmer and {fee if fee_netted else 0:,} UGX to MatookeSmart.",
        f"Farmer's total for this order (advance included): {farmer_total:,} UGX.",
    ]
    if refund_due:
        lines.append(
            f"The advance exceeds the value delivered by {refund_due:,} UGX. Repayment of that "
            "amount follows the agreed cancellation and crop-failure terms - it is not collected "
            "by MatookeSmart."
        )
    if shortfall and not refund_due:
        lines.append(
            f"Short by {shortfall} bunches. Record why (crop failure, labour, buyer refusal) "
            "in the order events before closing the order."
        )
    if not fee_netted and fee:
        lines.append(
            "The fee could not be netted from the balance because the balance was smaller than "
            "the fee; it stays payable under the disclosed terms."
        )
    return {
        "delivered_bunches": delivered,
        "shortfall_bunches": shortfall,
        "supplied_value_ugx": supplied_value,
        "service_fee_ugx": fee,
        "farmer_total_ugx": farmer_total,
        "advance_paid_ugx": advance_paid_ugx,
        "buyer_balance_due_ugx": buyer_balance,
        "to_farmer_at_settlement_ugx": to_farmer_now,
        "refund_due_to_buyer_ugx": refund_due,
        "fee_netted_at_settlement": fee_netted,
        "balance_due_ugx": buyer_balance,
        "advance_to_reconcile_ugx": refund_due,
        "lines": lines,
    }


def declare_crop_failure(*, order_status: str, verified: bool, days_to_delivery: int) -> dict:
    """Safeguard against crop failure, per section 5.4.

    The point is to keep a farmer who loses a bunch from being treated as a
    defaulter, while still protecting the buyer's money.
    """
    options = [
        "Agree a revised delivery date with the buyer and record it as an order event.",
        "Deliver the part you can and have the buyer pay for what was supplied.",
        "Cancel by agreement: the advance is repaid on the agreed schedule, not immediately demanded.",
        "Offer the equivalent value as processed product if the Hub is buying, so the buyer still receives value.",
    ]
    if not verified:
        options.append(
            "Ask the parish/district agricultural officer to visit or to accept a photo record, so "
            "the claim is documented rather than argued."
        )
    return {
        "status": order_status,
        "verified_by_officer": verified,
        "days_to_delivery": days_to_delivery,
        "recommended": options[0] if days_to_delivery > 7 else options[1],
        "options": options,
        "rule": "MatookeSmart does not guarantee that every farmer receives an advance; it also does not treat a documented crop failure as a debt to be collected by force.",
    }


def urgency_alternative(
    *,
    need_ugx: int,
    order: OrderTerms,
    spot_price_ugx_per_bunch: int | None = None,
    loan_rate_per_month: float = 0.10,
    months_to_harvest: int = 1,
) -> dict:
    """Frame the pre-order against the usual alternative - explicitly labelled.

    Returns the comparison only; it must not be worded as financial advice and
    the loan rate is an assumption to be measured in interviews.
    """
    advance = order.advance_ugx
    interest = int(need_ugx * loan_rate_per_month * max(months_to_harvest, 1))
    covers = advance >= need_ugx
    price_forgone = 0
    if spot_price_ugx_per_bunch:
        price_forgone = max(
            (spot_price_ugx_per_bunch - order.price_per_bunch_ugx) * order.quantity_bunches, 0
        )
    return {
        "advance_available_ugx": advance,
        "covers_need": covers,
        "gap_ugx": max(need_ugx - advance, 0),
        "illustrative_loan_interest_ugx": interest,
        "assumption": (
            f"Loan interest shown at {loan_rate_per_month * 100:.0f} % a month, which is an "
            "assumption to be verified with real rates in the district, not a quote."
        ),
        "price_forgone_ugx": int(price_forgone),
        "note": (
            "An advance is repaid with produce at a price both sides agreed. A loan is repaid with "
            "interest regardless of how the market moved. The trade-off is price certainty against "
            "obligation risk - the app states both."
        ),
    }


def sla_days(delivery_date: date, today: date | None = None) -> int:
    return (delivery_date - (today or date.today())).days


def suggest_delivery_date(harvest_date: date, *, buffer_days: int = 2) -> date:
    """Harvest day plus a short handling buffer; never earlier than harvest."""
    return harvest_date + timedelta(days=buffer_days)
