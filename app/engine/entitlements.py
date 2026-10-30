"""5.7 Membership: what each tier unlocks, and what must never be gated.

The proposal sets one hard rule that has to live in code, not in a design
document: "essential disease warnings and basic public agricultural
information should not be withheld from non-paying farmers". The
`SAFETY_CRITICAL` set below is therefore exempt from every gate, and a test
asserts that a free account still gets the farm-doctor advice.
"""

from __future__ import annotations

TIERS: dict[str, dict] = {
    "basic_farmer": {
        "label": "Basic Farmer (free)",
        "price_ugx_month": 0,
        "audience": "farmer",
        "access": "Basic market information, selected agricultural guidance, public opportunities, marketplace browsing",
    },
    "smart_farmer": {
        "label": "Smart Farmer (paid monthly)",
        "price_ugx_month": 10000,
        "audience": "farmer",
        "access": "Personalised price alerts, expanded farm records, extra advisory access, enhanced selling recommendations",
    },
    "professional_farmer": {
        "label": "Professional Farmer (paid monthly)",
        "price_ugx_month": 25000,
        "audience": "farmer",
        "access": "Advanced analytics, fuller farm records, priority access to selected buyer opportunities, business reports",
    },
    "buyer_institution": {
        "label": "Buyer / Institution",
        "price_ugx_month": 40000,
        "audience": "buyer",
        "access": "Supplier discovery, bulk-order tools, recurring procurement support, order history, optional analytics",
    },
}

# Never behind a paywall, whatever the tier (section 5.7).
SAFETY_CRITICAL = {
    "farm_doctor_advice",
    "disease_prevention_info",
    "bxw_outbreak_alert",
    "basic_price_trend",
    "public_opportunities",
    "marketplace_browse",
    "record_market_price",
    "early_order_education",
    "cancel_order",
}

GATED = {
    "price_alerts": {"smart_farmer", "professional_farmer"},
    "forecast_detail": {"smart_farmer", "professional_farmer"},
    "sell_recommendation_detail": {"smart_farmer", "professional_farmer"},
    "expanded_farm_records": {"smart_farmer", "professional_farmer"},
    "match_ranking_full": {"smart_farmer", "professional_farmer"},
    "business_reports": {"professional_farmer"},
    "advanced_analytics": {"professional_farmer"},
    "priority_buyer_access": {"professional_farmer"},
    "bulk_order_tools": {"buyer_institution"},
    "recurring_procurement": {"buyer_institution"},
    "supplier_discovery": {"buyer_institution"},
}


def is_gated(feature: str) -> bool:
    return feature in GATED


def allowed(tier: str, feature: str) -> bool:
    if feature in SAFETY_CRITICAL or feature not in GATED:
        return True
    return tier in GATED[feature]


def gate_note(tier: str, feature: str) -> str:
    if allowed(tier, feature):
        return ""
    need = sorted(GATED[feature])
    labels = [TIERS[t]["label"] for t in need if t in TIERS]
    return (
        f"'{feature.replace('_', ' ')}' is part of a paid tier ({' or '.join(labels)}). "
        "Disease warnings and basic market information stay free on every account."
    )


def tier_matrix() -> list[dict]:
    rows = []
    for key, meta in TIERS.items():
        rows.append(
            {
                "key": key,
                **meta,
                "features": sorted(f for f, tiers in GATED.items() if key in tiers),
                "price_is_hypothesis": True,
            }
        )
    return rows


def upsell_for(tier: str, feature: str) -> dict:
    """What to show a gated user instead of the feature."""
    if allowed(tier, feature):
        return {"show": False}
    targets = sorted(GATED[feature], key=lambda t: TIERS[t]["price_ugx_month"])
    nxt = targets[0]
    return {
        "show": True,
        "message": (
            f"Upgrade to {TIERS[nxt]['label']} ({TIERS[nxt]['price_ugx_month']:,} UGX a month, "
            "price still to be validated with farmers) to unlock this. Meanwhile the free "
            "information you need for plant health and market direction stays available."
        ),
        "tier": nxt,
        "price_ugx_month": TIERS[nxt]["price_ugx_month"],
    }
