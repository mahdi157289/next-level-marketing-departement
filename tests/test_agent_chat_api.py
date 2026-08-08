"""Agent-scoped chat + prompt API tests."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_threads_scoped_by_agent():
    from crm import service

    tag = uuid.uuid4().hex[:8]
    head_thread = service.create_scout_thread(f"head-{tag}", agent_name="head")
    discovery_thread = service.create_scout_thread(f"disc-{tag}", agent_name="discovery")
    try:
        heads = service.list_scout_threads(agent_name="head", limit=50)
        discs = service.list_scout_threads(agent_name="discovery", limit=50)
        assert any(t["id"] == head_thread["id"] for t in heads)
        assert not any(t["id"] == head_thread["id"] for t in discs)
        assert any(t["id"] == discovery_thread["id"] for t in discs)
    finally:
        eng = create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_messages WHERE thread_id IN (SELECT id FROM scout_threads WHERE id = ANY(CAST(:ids AS uuid[])))"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_threads WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        eng.dispose()
