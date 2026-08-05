"""Pipeline-run listing with agent-run counts — requires DATABASE_URL."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest

from crm import service


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_list_pipeline_runs_has_counts():
    run = service.start_pipeline_run("pytest", "list test", {"mode": "discovery_only"})
    rid = str(run["id"])
    try:
        service.start_agent_run(rid, "discovery", model="m", input_summary="s")
        rows = service.list_pipeline_runs(limit=50)
        assert any(str(r["id"]) == rid and r.get("agent_run_count", 0) >= 1 for r in rows), rows
    finally:
        eng = __import__("sqlalchemy").create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(__import__("sqlalchemy").text("DELETE FROM agent_runs WHERE pipeline_run_id = :id"), {"id": uuid.UUID(rid)})
            conn.execute(__import__("sqlalchemy").text("DELETE FROM pipeline_runs WHERE id = :id"), {"id": uuid.UUID(rid)})
        eng.dispose()
