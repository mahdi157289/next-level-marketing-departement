"""Lead Completion Agent + storage tests.

Pure-unit tests for name matching / gap planning / website extraction run
without a DB. DB-backed tests use real Postgres (DATABASE_URL) and clean up.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from crm import service
from db.models import Lead
from workflows.enrich_leads import _hit_to_lead_data, _lookup_maps_best, name_similarity


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


# --- name matching ---


def test_name_similarity_high_for_same_business():
    assert name_similarity("AS AGENCY - Agence Web Tunis", "AS AGENCY Agence Web Tunis") > 0.5


def test_name_similarity_high_for_identical():
    assert name_similarity("WEBI", "webi") == 1.0


def test_name_similarity_low_for_unrelated():
    assert name_similarity("Pizza Palace", "Web Media Tunisie") == 0.0


# --- gap planning ---


def test_lead_gaps_lists_only_empty_fillable_fields():
    lead = {
        "name": "X", "url": "https://x.tn",
        "phone": "+21600000000", "rating": 4.5,
        "email": "", "address": None, "review_count": 0, "tags": [],
    }
    gaps = service.lead_gaps(lead)
    assert "phone" not in gaps
    assert "rating" not in gaps
    assert "email" in gaps
    assert "address" in gaps
    assert "review_count" in gaps
    assert "tags" in gaps


def test_hit_to_lead_data_fills_only_gaps():
    lead = {"name": "X", "url": "https://x.tn", "phone": "+21600000000", "country": "Tunisia"}
    hit = {
        "address": "Tunis", "phone": "+21611111111", "rating": "4.9",
        "category": "Italian Restaurant", "google_maps_url": "https://google.com/maps/place/X",
    }
    data = _hit_to_lead_data(lead, hit)
    assert data.get("address") == "Tunis"
    assert data.get("rating") == "4.9"
    assert data.get("industry") == "Italian Restaurant"
    assert data.get("google_maps_url").startswith("https://google.com/maps")
    assert "phone" not in data  # already filled — never overwrite
    assert "country" not in data  # already filled


def test_lookup_maps_best_picks_best_match():
    hits = [
        {"title": "Something Else", "url": "https://else.tn"},
        {"title": "Web Media Tunisie", "url": "https://webmedia.tn", "address": "Tunis"},
    ]
    with _patch_search(hits):
        lead = {"name": "Web Media Tunisie", "url": "https://webmedia.tn", "country": "Tunisia"}
        best = _lookup_maps_best(lead)
    assert best is not None
    assert best["title"] == "Web Media Tunisie"


def test_lookup_maps_best_rejects_low_similarity():
    hits = [{"title": "Bakery Tunis", "url": "https://bakery.tn"}]
    with _patch_search(hits):
        lead = {"name": "Web Media Tunisie", "url": "https://webmedia.tn"}
        assert _lookup_maps_best(lead) is None


def _patch_search(hits):
    from unittest.mock import patch

    return patch("workflows.enrich_leads.resolve_callable", return_value=lambda *a, **k: hits)


# --- enrich_missing (DB) ---


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_missing_only_fills_empty_fields():
    url = _unique_url("missing")
    lead = service.create_lead(
        {"name": "FillCo", "url": url, "status": "raw", "source": "discovery", "phone": "+21611111111"}
    )
    try:
        out = service.enrich_missing(
            str(lead["id"]),
            {"phone": "+21699999999", "email": "ops@fillco.tn", "hours": "Mon-Fri 9-6"},
        )
        assert out is not None
        assert out["phone"] == "+21611111111"  # untouched
        assert out["email"] == "ops@fillco.tn"
        assert out["hours"] == "Mon-Fri 9-6"
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_missing_noop_when_nothing_empty():
    url = _unique_url("noop2")
    lead = service.create_lead(
        {"name": "NoopCo", "url": url, "status": "raw", "source": "discovery", "phone": "+21611111111"}
    )
    try:
        out = service.enrich_missing(str(lead["id"]), {"phone": "+21622222222"})
        assert out["phone"] == "+21611111111"
        assert out["status"] == "raw"
    finally:
        _cleanup(url)


# --- persistence of new fields ---


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_create_lead_from_hit_persists_completion_fields():
    url = _unique_url("completion")
    hit = {
        "title": "Complete Co",
        "url": url,
        "phone": "+21633333333",
        "category": "Software",
        "hours": "Mon-Fri 9:00-18:00",
        "description": "A complete description",
        "price_level": "$$",
        "facebook": "https://facebook.com/completeco",
        "instagram": "https://instagram.com/completeco",
        "linkedin": "https://linkedin.com/company/completeco",
        "twitter": "https://twitter.com/completeco",
        "tags": ["SaaS", "Startup"],
    }
    try:
        lead = service.create_lead_from_search_hit(hit, agent_run_id=None)
        assert lead.get("created") is True
        assert lead["hours"] == "Mon-Fri 9:00-18:00"
        assert lead["description"] == "A complete description"
        assert lead["price_level"] == "$$"
        assert lead["facebook"] == "https://facebook.com/completeco"
        assert lead["instagram"] == "https://instagram.com/completeco"
        assert lead["linkedin"] == "https://linkedin.com/company/completeco"
        assert lead["twitter"] == "https://twitter.com/completeco"
        assert lead["tags"] == ["SaaS", "Startup"]
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_lead_persists_new_fields():
    url = _unique_url("enrichnew")
    lead = service.create_lead({"name": "NewFields", "url": url, "status": "raw", "source": "discovery"})
    try:
        out = service.enrich_lead(
            str(lead["id"]),
            {"hours": "Open 24h", "price_level": "$", "tags": ["Local"], "instagram": "https://ig/newfields"},
        )
        assert out["hours"] == "Open 24h"
        assert out["price_level"] == "$"
        assert out["tags"] == ["Local"]
        assert out["instagram"] == "https://ig/newfields"
        assert out["status"] == "enriched"
    finally:
        _cleanup(url)


# --- website extraction helpers ---


def test_scrape_tool_socials_and_description_extraction():
    from tools.scrape_tool import _extract_description, _extract_socials, _clean_phone

    html = (
        '<meta property="og:description" content="Best agency in Tunis">'
        '<a href="https://www.facebook.com/acme">fb</a>'
        '<a href="https://www.instagram.com/acme">ig</a>'
    )
    socials = _extract_socials(html)
    assert socials["facebook"] == "https://facebook.com/acme"
    assert socials["instagram"] == "https://instagram.com/acme"
    assert "Best agency" in _extract_description(html)

    assert _clean_phone("+216 71 000 000") == "+216 71 000 000"
    assert _clean_phone("123") is None  # too few digits
    assert _clean_phone("+216 CALL ME") is None  # contains letters


def test_google_maps_place_parses_lead():
    import json
    from unittest.mock import MagicMock, patch

    from tools.google_maps_tool import google_maps_place

    raw_lead = {
        "name": "Place One", "category": "Agency", "rating": "4.5",
        "reviewsCount": "12", "address": "Tunis", "phone": "+21671000000",
        "website": "https://place-one.tn", "url": "https://google.com/maps/place/Place+One",
        "email": "hi@place-one.tn",
    }
    line = json.dumps({"type": "lead", "data": raw_lead}) + "\n"
    proc = MagicMock()
    proc.communicate.return_value = (line, "")
    with patch("tools.google_maps_tool.subprocess.Popen", return_value=proc):
        hit = google_maps_place("https://www.google.com/maps/place/Place+One")

    assert hit is not None
    assert hit["title"] == "Place One"
    assert hit["email"] == "hi@place-one.tn"
    assert hit["rating"] == "4.5"
    assert hit["google_maps_url"] == "https://google.com/maps/place/Place+One"


# --- hunt step (research summary) ---


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_one_hunts_missing_fields():
    from unittest.mock import patch

    from crm.client import _AgentRunContext
    from workflows.enrich_leads import _enrich_one

    url = _unique_url("huntstep")
    lead = service.create_lead({
        "name": "HuntStep Co", "url": url, "source": "pytest",
        "google_maps_url": "https://google.com/maps/place/x",
        "address": "Tunis", "rating": 4.5, "review_count": 10,
        "country": "Tunisia", "industry": "Software", "business_type": "software",
        "email": "a@huntstep.tn", "phone": "+21611111111", "seo_score": 80,
        "hours": "Mon-Fri", "description": "d", "price_level": "$$",
        "facebook": "https://fb.co/h", "instagram": "https://ig.co/h",
        "linkedin": "https://ln.co/h", "twitter": "https://x.co/h", "tags": ["x"],
    })
    pipeline = service.start_pipeline_run("pytest", "hunt-step", {})
    agent_run = service.start_agent_run(
        str(pipeline["id"]), "enrich", model="n/a", input_summary="hunt-step-test"
    )
    try:
        fake = {
            "summary": "HuntStep summary",
            "fields_found": {"email": "ops@huntstep.tn", "facebook": "https://facebook.com/huntstep"},
            "sources": [{"title": "t", "url": "https://s.tn", "snippet": "s"}],
            "queries": ["q"], "status": "ok",
        }
        run = _AgentRunContext(str(agent_run["id"]))
        with patch("workflows.enrich_leads.resolve_callable", return_value=lambda *a, **k: fake):
            res = _enrich_one(lead, run, lambda: False)
        assert "hunt" in res["steps"]
        fresh = service.get_lead(str(lead["id"]))
        assert fresh["research"]["summary"] == "HuntStep summary"
        assert fresh["research"]["fields_found"]["email"] == "ops@huntstep.tn"
        assert fresh["email"] == "a@huntstep.tn"  # gap-only: pre-filled field untouched
    finally:
        _cleanup(url)
        service.complete_agent_run(str(agent_run["id"]), "success")
        service.complete_pipeline_run(str(pipeline["id"]), "cancelled", {"reason": "test_cleanup"})
