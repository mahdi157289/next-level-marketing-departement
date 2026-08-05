"""CRM tool — thin wrappers for agents; lead I/O delegates to crm.service."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from crm import service
from db.session import engine


def crm_read_tool(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Read leads from PostgreSQL, optionally filtered by status."""
    return service.list_leads(status=status, limit=limit)


def crm_write_tool(table: str, data: Dict[str, Any], where_id: Optional[str] = None) -> str:
    """Insert or update a row and return a marker string with row id."""
    if table == "leads":
        if where_id:
            updated = service.update_lead(where_id, data)
            if not updated:
                raise ValueError(f"Lead not found: {where_id}")
            return f"updated:{where_id}"
        created = service.create_lead(data)
        return f"inserted:{created['id']}"

    allowed_tables = {"company_knowledge", "outreach_records", "campaign_metrics", "task_log"}
    if table not in allowed_tables:
        raise ValueError(f"Unsupported table: {table}")

    with engine.begin() as conn:
        if where_id:
            assignments = ", ".join([f"{column}=:{column}" for column in data])
            payload = dict(data)
            payload["_id"] = where_id
            conn.execute(text(f"UPDATE {table} SET {assignments} WHERE id = :_id"), payload)
            return f"updated:{where_id}"

        payload = dict(data)
        payload.setdefault("id", str(uuid.uuid4()))
        columns = ", ".join(payload.keys())
        values = ", ".join([f":{column}" for column in payload.keys()])
        result = conn.execute(
            text(f"INSERT INTO {table} ({columns}) VALUES ({values}) RETURNING id"),
            payload,
        )
        inserted_id = result.scalar_one()
        return f"inserted:{inserted_id}"
