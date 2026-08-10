"""CRM growth — enrichment data persists onto leads and status flows raw→enriched.

Real Postgres (DATABASE_URL), no leftover mock leads after each test.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from crm import service
from db.models import Lead


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _unique_url(seed: str) -> str:
    return f"https://enrich-{seed}-{uuid.uuid4().hex[:8]}.tn"


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(Lead).where(Lead.url == url))
        conn.commit()
    eng.dispose()


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_create_lead_from_hit_persists_structured_fields():
    url = _unique_url("maps")
    hit = {
        "title": "Pizza Palace Tunis",
        "url": url,
        "snippet": "Best pizza in town",
        "phone": "+21671000000",
        "category": "Italian Restaurant",
        "country": "Tunisia",
    }
    try:
        lead = service.create_lead_from_search_hit(hit, agent_run_id=None)
        assert lead.get("created") is True
        assert lead["phone"] == "+21671000000"
        assert lead["industry"] == "Italian Restaurant"
        assert lead["country"] == "Tunisia"
        assert lead["status"] == "raw"
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_lead_sets_enriched_status_and_events():
    url = _unique_url("enrich")
    pipeline = service.start_pipeline_run("pytest", "crm-growth", {})
    agent_run = service.start_agent_run(
        str(pipeline["id"]), "discovery", model="n/a", input_summary="enrich-test"
    )
    lead = service.create_lead(
        {"name": "LogiTunis", "url": url, "status": "raw", "source": "discovery"}
    )
    try:
        out = service.enrich_lead(
            str(lead["id"]),
            {"email": "ops@logitunis.tn", "phone": "+21622000000", "seo_score": 42},
            agent_run_id=str(agent_run["id"]),
        )
        assert out is not None
        assert out["email"] == "ops@logitunis.tn"
        assert out["phone"] == "+21622000000"
        assert out["seo_score"] == 42
        assert out["status"] == "enriched"

        detail = service.get_lead(str(lead["id"]))
        events = detail.get("events") or []
        types = [e["event_type"] for e in events]
        assert "enriched" in types
        assert "status_changed" in types
    finally:
        _cleanup(url)
        service.complete_agent_run(str(agent_run["id"]), "success")
        service.complete_pipeline_run(str(pipeline["id"]), "cancelled", {"reason": "test_cleanup"})


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_lead_noop_when_no_new_fields():
    url = _unique_url("noop")
    lead = service.create_lead(
        {"name": "NoopCo", "url": url, "status": "raw", "source": "discovery"}
    )
    try:
        out = service.enrich_lead(str(lead["id"]), {"phone": None, "unknown_field": "x"})
        assert out is not None
        assert out["status"] == "raw"
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_existing_lead_on_rediscovery():
    url = _unique_url("redis")
    lead = service.create_lead(
        {"name": "ExistingCo", "url": url, "status": "raw", "source": "discovery"}
    )
    try:
        hit = {
            "title": "ExistingCo",
            "url": url,
            "snippet": "re-discovery",
            "phone": "+21633333333",
            "category": "Logistics",
        }
        again = service.create_lead_from_search_hit(hit, agent_run_id=None)
        assert again.get("created") is False
        assert again["id"] == lead["id"]
        assert again["phone"] == "+21633333333"
        assert again["industry"] == "Logistics"
    finally:
        _cleanup(url)
