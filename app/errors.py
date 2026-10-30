"""Friendly errors: JSON for /api, a readable page for screens. No stack traces leak."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .pages import ctx, templates

log = logging.getLogger("matookesmart")

TITLES = {404: "Page not found", 405: "Not allowed", 429: "Please slow down"}


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
        return templates.TemplateResponse(
            request,
            "message.html",
            ctx(request, title=TITLES.get(exc.status_code, "Something went wrong"), message=str(exc.detail), back="/dashboard"),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "-")
        log.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
        msg = f"Something went wrong on our side. Quote reference {rid} if you report it."
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": msg, "request_id": rid}, status_code=500)
        return templates.TemplateResponse(
            request, "message.html", ctx(request, title="Something went wrong", message=msg, back="/"), status_code=500
        )
