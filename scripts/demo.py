#!/usr/bin/env python3
"""One-command walkthrough of every module, printed to the terminal.

Useful for a viva, a marker, or anyone who wants to see the engines without
opening a browser:

    python scripts/demo.py --quantity 120 --urgent 400000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models, services
from app.db import SessionLocal, init_db
from app.engine import diseases, products


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    ap = argparse.ArgumentParser(description="MatookeSmart Companion engine walkthrough")
    ap.add_argument("--farm", type=int, default=1, help="farm id, 1-4 in the demo data")
    ap.add_argument("--quantity", type=int, default=0, help="bunches, 0 = use the farm's listing")
    ap.add_argument("--urgent", type=int, default=0, help="urgent cash need in UGX")
    ap.add_argument("--horizon", type=int, default=75, help="forecast horizon in days")
    ap.add_argument("--fresh-kg", type=float, default=400, help="fresh surplus for processing maths")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        farm = db.get(models.Farm, args.farm)
        if not farm:
            print(f"No farm {args.farm}. Run:  python -m app.seed", file=sys.stderr)
            return 1

        rule(f"5.2  MARKET INTELLIGENCE - {farm.owner.full_name}, {farm.district}")
        view = services.advice_for_farm(
            db,
            farm,
            urgent_need_ugx=args.urgent,
            horizon_days=args.horizon,
            quantity_bunches=args.quantity or None,
        )
        fc = view["forecast"]
        print(f"Market            : {view['market'].name} ({view['market'].district})")
        print(f"Records used      : {fc.n_records} ({fc.n_verified} verified) over {fc.span_days} days")
        print(f"Latest recorded   : {fc.latest_price_ugx:,} UGX per bunch on {fc.latest_day}")
        print(f"Moving averages   : short {fc.ma7_ugx:,} / long {fc.ma28_ugx:,} UGX")
        print(f"Trend (de-seasoned): {fc.trend_pct_per_month:+.2f} % per month")
        print(f"Backtested MAPE   : {fc.mape_pct if fc.mape_pct is not None else 'n/a'} %")
        print(f"Confidence        : {fc.confidence}")
        print(f"Summary           : {fc.summary()}")
        print(
            "Seasonal index    : "
            + ", ".join(f"{k[:3]} {v:+.2f}" for k, v in list(fc.seasonal_index.items())[:6])
            + " ..."
        )
        for c in fc.caveats:
            print(f"  ! {c}")

        rule("5.2  WHAT SHOULD I DO WITH MY MATOOKE?")
        advice = view["advice"]
        print(advice.headline)
        print(f"\nPrimary route: {advice.primary_option}")
        for o in advice.options:
            print(f"\n  [{o.key}] {o.label}")
            print(
                f"      net {o.expected_net_ugx:,} UGX  ({o.delta_vs_sell_now_ugx:+,} vs selling today)  {o.certainty}"
            )
            print(f"      {o.detail}")
            if o.risks:
                print(f"      watch: {o.risks[0]}")
        if advice.urgent_need_note:
            print(f"\n  Cash need: {advice.urgent_need_note}")
        for a in advice.alerts:
            print(f"  alert: {a}")

        rule("5.1  FARM DOCTOR - worked BXW-style example")
        answers = {
            "speed": "days",
            "pattern": "one",
            "fruit": "premature",
            "bud": "black",
            "inside": "brown",
            "leaves": "yellow",
        }
        result = diseases.assess(answers)
        print(services.doctor_assess(answers)["headline"])
        for c in result.candidates:
            print(f"  {c.confidence:5.0%}  {c.name}")
        print(f"  referred: {result.referred}")
        if result.referral_reason:
            print(f"  why     : {result.referral_reason}")
        if result.advice:
            print("  do now  : " + result.advice["immediate_actions"][0])
            print("  prevent : " + result.advice["prevention"][0])
        if result.next_question:
            print(f"  next ask: {result.next_question['text']}")

        rule("5.3  SURPLUS: RANKED PROCESSING OPTIONS")
        print(f"Assumed {args.fresh_kg:g} kg fresh ({args.fresh_kg / 27:.1f} bunches at 27 kg)")
        for r in view["recommendations"]:
            print(
                f"  {r['score']:.2f}  {r['product_name']:<34} {r['verdict']:<20} "
                f"yield {r['yield_pct']:5.1f} %  margin {r['margin_pct']:+6.1f} %  [{r['source']}]"
            )
        print(f"\n{products.catalog()['notice'][:150]}...")

        rule("5.5  BUYER MATCHING")
        for m in services.match_suggestions(db)[:4]:
            print(
                f"  {m['score']:.2f}  {m['farmer_name']} -> {m['buyer_name']}: "
                f"{m['quantity_bunches']} bunches at {m['suggested_price_ugx_per_bunch']:,} UGX "
                f"({m['order_value_ugx']:,} UGX), {m['distance_km'] or '?'} km"
            )
            for e in m["explanations"][:2]:
                print(f"        - {e}")

        rule("5.4  EARLY ORDERS IN FLIGHT")
        for row in db.query(models.EarlyOrder).all():
            o = services.order_view(db, row)
            print(
                f"  {o['reference']:<18} {o['status']:<12} {o['quantity_bunches']:>4} bunches "
                f"@ {o['price_per_bunch_ugx']:,}  advance {o['advance_paid_ugx']:,}  "
                f"balance {o['balance_due_ugx']:,}  fee {o['service_fee_ugx']:,}"
            )
            print(
                f"        delivery {o['delivery_date']} "
                f"({(o['delivery_date'] - date.today()).days} days from today), "
                f"{len(o['events'])} recorded events"
            )

        rule("5.6  VERIFIED OPPORTUNITIES")
        for i in services.opportunity_list(db, district=farm.district):
            print(f"  [{i['effective']['status']:<12}] {i['title']}")
            print(f"        {i['source_line']}")
        if view["hub_note"]:
            print(f"\n  Hub: {view['hub_note']}")

        print("\nReminder: every price, yield and cost in this run is synthetic sample data.")
        print(
            f"Started {date.today()} - expected harvest was {farm.expected_harvest_date} "
            f"({(farm.expected_harvest_date - date.today()).days} days out).\n"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
