import os
import uuid

from sqlalchemy import create_engine, text

from tools.crm_tool import crm_read_tool, crm_write_tool

# DuckDuckGo live tests moved to tests/test_live.py — no mocks.


def test_crm_roundtrip():
    """Real PostgreSQL insert + read — requires DATABASE_URL and migrated schema.

    Temporary fixture row is deleted in finally so shared CRM stays clean.
    """
    unique = str(uuid.uuid4())[:8]
    url = f"https://tooltest-{unique}.example.com"
    lead_id = None
    try:
        marker = crm_write_tool(
            "leads",
            {
                "name": f"Tool Test {unique}",
                "url": url,
                "status": "raw",
                "source": "pytest",
            },
        )
        assert marker.startswith("inserted:")
        lead_id = marker.split(":", 1)[1]
        rows = crm_read_tool(status="raw", limit=200)
        assert any(r.get("url") == url for r in rows)
    finally:
        db_url = os.getenv("DATABASE_URL")
        if db_url and lead_id:
            eng = create_engine(db_url)
            with eng.begin() as conn:
                conn.execute(text("DELETE FROM lead_events WHERE lead_id = :id"), {"id": lead_id})
                conn.execute(text("DELETE FROM leads WHERE id = :id"), {"id": lead_id})
