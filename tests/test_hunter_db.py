"""DB tests for the hunter research column."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from crm import service
from db.models import Lead


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(Lead).where(Lead.url == url))
        conn.commit()
    eng.dispose()


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_lead_research_roundtrip():
    url = f"https://hunt-db-{uuid.uuid4().hex[:8]}.tn"
    lead = service.create_lead({"name": "Hunt DB Co", "url": url, "source": "pytest"})
    try:
        out = service.enrich_missing(
            str(lead["id"]),
            {"research": {"summary": "x", "fields_found": {"email": "a@b.tn"}, "status": "ok"}},
        )
        assert out["research"]["summary"] == "x"
        assert out["research"]["fields_found"]["email"] == "a@b.tn"
    finally:
        _cleanup(url)
