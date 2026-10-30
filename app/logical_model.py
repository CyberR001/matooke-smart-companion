"""Logical view of the data model, read live from the SQLAlchemy metadata.

Nothing here is hand-drawn: the /system screen, the /api/v1/system endpoint and
docs/LOGICAL_MODEL.md are all generated from the same tables the database uses,
so the diagram cannot drift away from the code.
"""

from __future__ import annotations

import re

from . import models  # noqa: F401  (registers every table on Base.metadata)
from .db import Base

# Business grouping of tables (proposal sections 5.1-5.7). Any table that is not
# listed falls into "Other", so a new model is never silently hidden.
DOMAINS: dict[str, list[str]] = {
    "People and access (5.7)": ["person", "subscription", "farm"],
    "Market intelligence (5.2)": ["market", "price_record", "forecast_run"],
    "Farm doctor (5.1)": ["disease_case"],
    "Hub and products (5.3)": ["product_trial", "hub_buying_notice"],
    "Marketplace and early orders (5.4, 5.5)": [
        "harvest_listing", "buyer_requirement", "match_run", "early_order", "order_event",
    ],
    "Opportunities (5.6)": ["opportunity"],
}


def _entity(table) -> dict:
    return {
        "table": table.name,
        "columns": [
            {
                "name": c.name,
                "type": re.sub(r"\(.*\)", "", str(c.type)).strip() or "TEXT",
                "pk": bool(c.primary_key),
                "fk": sorted(f.target_fullname for f in c.foreign_keys),
                "nullable": bool(c.nullable),
            }
            for c in table.columns
        ],
    }


def describe() -> list[dict]:
    tables = Base.metadata.tables
    seen: set[str] = set()
    out: list[dict] = []
    for domain, names in DOMAINS.items():
        ents = [_entity(tables[n]) for n in names if n in tables]
        seen.update(e["table"] for e in ents)
        out.append({"domain": domain, "entities": ents})
    rest = [_entity(t) for n, t in sorted(tables.items()) if n not in seen]
    if rest:
        out.append({"domain": "Other", "entities": rest})
    return out


def relationships() -> list[dict]:
    rels = []
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                parent = fk.column.table.name
                rels.append({"child": table.name, "parent": parent, "column": col.name})
    return rels


def mermaid_er() -> str:
    lines = ["erDiagram"]
    for rel in relationships():
        lines.append(f'  {rel["parent"]} ||--o{{ {rel["child"]} : "{rel["column"]}"')
    for dom in describe():
        for ent in dom["entities"]:
            lines.append(f'  {ent["table"]} {{')
            for c in ent["columns"]:
                key = " PK" if c["pk"] else (" FK" if c["fk"] else "")
                typ = re.sub(r"\W", "", c["type"]) or "TEXT"
                lines.append(f'    {typ} {c["name"]}{key}')
            lines.append("  }")
    return "\n".join(lines)
