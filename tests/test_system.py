from __future__ import annotations

from app import logical_model
from app.config import settings
from app.db import Base


def test_system_page_renders(client):
    r = client.get("/system")
    assert r.status_code == 200
    assert "Logical data model" in r.text and "early_order" in r.text


def test_logical_model_covers_every_table(client):
    listed = {e["table"] for d in logical_model.describe() for e in d["entities"]}
    assert listed == set(Base.metadata.tables)
    assert "erDiagram" in logical_model.mermaid_er()


def test_system_api_marks_placeholders(client):
    data = client.get("/api/v1/system").json()
    status = {m["name"]: m["status"] for m in data["modules"]}
    assert status["Farm doctor"] == "prototype" and status["Price forecast"] == "prototype"
    assert data["relationships"]


def test_security_headers_and_request_id(client):
    r = client.get("/", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_friendly_404_for_pages_and_json_for_api(client):
    page = client.get("/nope")
    assert page.status_code == 404 and "text/html" in page.headers["content-type"]
    assert client.get("/api/v1/nope").json()["detail"]


def test_rate_limit_on_writes(client):
    settings.rate_limit_per_min = 2
    try:
        codes = [client.post("/api/v1/matches/run", headers={"x-forwarded-for": "9.9.9.9"}).status_code for _ in range(4)]
    finally:
        settings.rate_limit_per_min = 0
    assert 429 in codes
