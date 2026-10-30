"""Regenerate docs/LOGICAL_MODEL.md from the live SQLAlchemy metadata.

    python -m scripts.gen_logical_model
"""

from __future__ import annotations

from pathlib import Path

from app import logical_model

out = ["# Logical data model", "",
       "Generated from `app/models.py` by `scripts/gen_logical_model.py`. Do not edit by hand.", "",
       "```mermaid", logical_model.mermaid_er(), "```", ""]
for d in logical_model.describe():
    out += [f"## {d['domain']}", ""]
    for e in d["entities"]:
        out += [f"### `{e['table']}`", "", "| Field | Type | Key |", "| --- | --- | --- |"]
        for c in e["columns"]:
            key = "PK" if c["pk"] else (f"FK -> {c['fk'][0].split('.')[0]}" if c["fk"] else "")
            out.append(f"| {c['name']} | {c['type']} | {key} |")
        out.append("")
Path("docs/LOGICAL_MODEL.md").write_text("\n".join(out), encoding="utf-8")
print("wrote docs/LOGICAL_MODEL.md")
