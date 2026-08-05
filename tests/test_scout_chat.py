"""DB round-trip for scout chat tables — requires DATABASE_URL (like test_crm_api.py)."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_scout_tables_exist_and_roundtrip():
    eng = create_engine(_database_url())
    thread_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    try:
        with eng.begin() as conn:
            conn.execute(
                text("INSERT INTO scout_threads (id, title, created_at, updated_at) "
                     "VALUES (:id, :title, NOW(), NOW())"),
                {"id": thread_id, "title": "plan-test"},
            )
            conn.execute(
                text("INSERT INTO scout_messages (id, thread_id, role, content, tool_name, "
                     "tool_args, tool_result, created_at) "
                     "VALUES (:id, :thread_id, :role, :content, :tool_name, :tool_args, :tool_result, NOW())"),
                {
                    "id": msg_id,
                    "thread_id": thread_id,
                    "role": "assistant",
                    "content": "hello",
                    "tool_name": None,
                    "tool_args": None,
                    "tool_result": None,
                },
            )
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT role, content FROM scout_messages WHERE id = :id"),
                {"id": msg_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "assistant"
            assert row[1] == "hello"
    finally:
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM scout_messages WHERE id = :id"), {"id": msg_id})
            conn.execute(text("DELETE FROM scout_threads WHERE id = :id"), {"id": thread_id})
        eng.dispose()
