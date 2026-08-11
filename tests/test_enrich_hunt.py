# tests/test_enrich_hunt.py
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
    return f"https://hunt-{seed}-{uuid.uuid4().hex[:8]}.tn"


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(Lead).where(Lead.url == url))
        conn.commit()
    eng.dispose()


def test_lead_problems_lists_unrealistic_values():
    lead = {"rating": 11, "email": "N/A", "industry": "Software", "phone": "+216 71 000 000"}
    problems = service.lead_problems(lead)
    assert set(problems) == {"rating", "email"}
    assert problems["rating"] == "unrealistic"


def test_lead_problems_ignores_empty_and_valid():
    lead = {"rating": None, "email": "", "industry": "Software", "seo_score": 80}
    assert service.lead_problems(lead) == {}


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_hunt_fills_empty_and_fixes_unrealistic():
    url = _unique_url("fill")
    lead = service.create_lead({
        "name": "Hunt Co", "url": url, "status": "raw", "source": "discovery",
        "email": "bad", "phone": "+216 11 111 111",
    })
    try:
        out = service.enrich_hunt(str(lead["id"]), {
            "email": "ops@huntco.tn",       # current unrealistic -> overwrite
            "phone": "+216 99 999 999",     # current valid -> keep
            "hours": "Mon-Fri 9:00-18:00",  # empty -> fill
        })
        assert out is not None
        assert out["email"] == "ops@huntco.tn"
        assert out["phone"] == "+216 11 111 111"
        assert out["hours"] == "Mon-Fri 9:00-18:00"
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_hunt_never_regresses_good_data():
    url = _unique_url("keep")
    lead = service.create_lead({
        "name": "Keep Co", "url": url, "status": "raw", "source": "discovery",
        "email": "hi@keepco.tn", "phone": "+216 11 111 111",
    })
    try:
        out = service.enrich_hunt(str(lead["id"]), {
            "email": "other@keepco.tn",
            "phone": "+216 11 111 111",
        })
        assert out["email"] == "hi@keepco.tn"
        assert out["phone"] == "+216 11 111 111"
    finally:
        _cleanup(url)