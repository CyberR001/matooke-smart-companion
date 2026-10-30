"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import errors, pages
from .api import router as api_router
from .config import settings
from .db import SessionLocal, init_db
from .middleware import RateLimitMiddleware, RequestContextMiddleware
from .routers import system

DESCRIPTION = """
MatookeSmart Companion - working prototype of the venture described in the
concept proposal: a farmer companion (farm doctor, market intelligence and
'when to sell', surplus and trending products), an early-order marketplace,
and the commercial arm (MatookeSmart Hub) that buys suitable surplus.

All prices, yields and costs in the seeded database are synthetic sample data
for demonstration. Outputs are decision support, not guarantees.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.seed_demo_data:
        from sqlalchemy import select

        from . import models
        from . import seed as seed_module

        db = SessionLocal()
        try:
            has_people = db.scalars(select(models.Person).limit(1)).first() is not None
            if not has_people:
                seed_module.seed(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if settings.cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
errors.install(app)

app.mount("/static", StaticFiles(directory=str(pages.BASE / "static")), name="static")
app.include_router(api_router)
app.include_router(system.api)
app.include_router(system.pages)
app.include_router(pages.router)


@app.get("/robots.txt", include_in_schema=False)
def robots():
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("User-agent: *\nAllow: /\n")
