"""Durable cache of crawled pages + auto-indexing into the RAG vector store."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.models import CrawlPage
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def save_crawl(
    url: str,
    *,
    title: str = "",
    domain: str = "",
    markdown: str = "",
    fields: Optional[Dict[str, Any]] = None,
    status: str = "ok",
    source: str = "site_extract",
    tags: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Insert or update a crawl record (keyed on url). Never raises."""
    try:
        session = SessionLocal()
        try:
            row = session.scalars(
                select(CrawlPage).where(CrawlPage.url == url)
            ).first()
            if row is None:
                row = CrawlPage(
                    id=uuid.uuid4(), url=url, title=title or "", domain=domain,
                    markdown=markdown or "", fields=fields or {}, status=status,
                    source=source, tags=tags or [], fetched_at=datetime.utcnow(),
                )
                session.add(row)
            else:
                row.title = title or row.title
                row.domain = domain or row.domain
                row.markdown = markdown or row.markdown
                row.fields = fields if fields is not None else row.fields
                row.status = status
                row.source = source
                if tags is not None:
                    row.tags = tags
                row.fetched_at = datetime.utcnow()
            session.commit()
            return _row_to_dict(row)
        finally:
            session.close()
    except BaseException as e:  # noqa: BLE001
        logger.warning("crawl_store.save_crawl failed for %s: %s", url, e)
        return None


def get_crawl(url: str) -> Optional[Dict[str, Any]]:
    try:
        session = SessionLocal()
        try:
            row = session.scalars(
                select(CrawlPage).where(CrawlPage.url == url)
            ).first()
            return _row_to_dict(row) if row else None
        finally:
            session.close()
    except BaseException:  # noqa: BLE001
        return None


def list_crawls(domain: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        session = SessionLocal()
        try:
            q = select(CrawlPage).order_by(CrawlPage.fetched_at.desc()).limit(limit)
            if domain:
                q = q.where(CrawlPage.domain == domain)
            return [_row_to_dict(r) for r in session.scalars(q).all()]
        finally:
            session.close()
    except BaseException:  # noqa: BLE001
        return []


def _row_to_dict(row: CrawlPage) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "url": row.url,
        "title": row.title,
        "domain": row.domain,
        "markdown": row.markdown,
        "fields": row.fields,
        "status": row.status,
        "source": row.source,
        "tags": row.tags,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }
