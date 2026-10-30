"""'How it fits together' - architecture, module status and the logical data model."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import logical_model
from ..config import settings
from ..pages import ctx, templates

api = APIRouter(prefix="/api/v1", tags=["system"])
pages = APIRouter()

LAYERS = [
    ("Experience", "Mobile-first screens (server-rendered, work without JavaScript). A later SMS/WhatsApp bridge or mobile app would call the same API.", "app/pages.py, templates/, static/"),
    ("Interface", "FastAPI routers and Pydantic schemas: validation, status codes, explicit refusals.", "app/api.py, app/routers/, app/schemas.py"),
    ("Application", "Services glue database rows to engines and compose one decision per farm.", "app/services.py"),
    ("Intelligence", "Pure-function engines with no web or ORM imports. Confidence and limits are returned as data.", "app/engine/"),
    ("Data", "SQLAlchemy 2.0 models. SQLite for demos, PostgreSQL in production.", "app/models.py, app/db.py"),
    ("Cross-cutting", "Settings, security headers, request IDs, rate limiting, friendly error pages.", "app/config.py, middleware.py, errors.py"),
]

# status: "working" | "prototype". The two prototype modules are deliberately
# left as placeholders and are labelled as such everywhere in the UI.
MODULES = [
    ("5.1", "Farm doctor", "prototype", "Rule-based questionnaire with expert-reviewable knowledge base. Image-based AI diagnosis is NOT built (placeholder in ml/)."),
    ("5.2", "Price forecast", "prototype", "Statistical baseline with backtested confidence. Not validated on real data; synthetic prices."),
    ("5.2", "When to sell", "working", "Ranked, priced options; refuses to say 'wait' when forecast confidence is low."),
    ("5.3", "Surplus and value addition", "working", "Yield, cost stack, margin and break-even; trials override assumptions."),
    ("5.4", "Early orders", "working", "Terms, deposit cap, settlement split, state machine, crop-failure path."),
    ("5.5", "Buyer matching", "working", "Explainable scoring on distance, quantity, timing, price and grade."),
    ("5.6", "Opportunities", "working", "Verification, expiry and staleness rules."),
    ("5.7", "Membership", "working", "Four tiers; safety-critical information never gated."),
]


def payload() -> dict:
    return {
        "app": settings.app_name,
        "layers": [{"name": n, "role": r, "code": c} for n, r, c in LAYERS],
        "modules": [{"proposal": p, "name": n, "status": s, "note": t} for p, n, s, t in MODULES],
        "logical_model": logical_model.describe(),
        "relationships": logical_model.relationships(),
    }


@api.get("/system")
def system_overview() -> dict:
    return payload()


@pages.get("/system", response_class=HTMLResponse)
def system_page(request: Request) -> HTMLResponse:
    data = payload()
    return templates.TemplateResponse(
        request,
        "system.html",
        ctx(request, **data, mermaid=logical_model.mermaid_er(), table_count=sum(len(d["entities"]) for d in data["logical_model"])),
    
    )
