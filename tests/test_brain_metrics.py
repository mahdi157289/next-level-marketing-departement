"""P4 — brain_query_metrics telemetry (real Postgres, DB-gated)."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_record_and_recent_roundtrip():
    from db.brain_metrics import recent_queries, record_query

    h = "testhash-" + uuid.uuid4().hex[:8]
    record_query("pytest", "tn", h, 12, False, 2, 1, query="what we offer")
    rows = recent_queries(limit=5)
    assert any(r["query_hash"] == h for r in rows)
    row = next(r for r in rows if r["query_hash"] == h)
    assert row["query"] == "what we offer"
    assert row["cache_hit"] is False
    assert row["vector_hits"] == 2
    assert row["graph_hits"] == 1
    assert row["created_at"] is not None
