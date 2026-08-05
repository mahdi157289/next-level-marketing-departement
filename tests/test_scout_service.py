"""Service-layer tests for scout chat — requires DATABASE_URL."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest

from crm import service


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_scout_thread_and_message_crud():
    thread = service.create_scout_thread("test thread")
    tid = str(thread["id"])
    try:
        assert thread["title"] == "test thread"

        m1 = service.add_scout_message(tid, "user", content="find leads")
        m2 = service.add_scout_message(tid, "assistant", content="done", tool_name="web_search")
        assert m1["role"] == "user"
        assert m2["tool_name"] == "web_search"

        msgs = service.list_scout_messages(tid)
        assert [m["role"] for m in msgs] == ["user", "assistant"]

        threads = service.list_scout_threads(limit=50)
        assert any(str(t["id"]) == tid for t in threads)
    finally:
        eng = __import__("sqlalchemy").create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(__import__("sqlalchemy").text("DELETE FROM scout_messages WHERE thread_id = :id"), {"id": uuid.UUID(tid)})
            conn.execute(__import__("sqlalchemy").text("DELETE FROM scout_threads WHERE id = :id"), {"id": uuid.UUID(tid)})
        eng.dispose()
