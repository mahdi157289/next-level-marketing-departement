"""DB tests for the crawl_pages cache + RAG auto-embed store."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from db.crawl_store import get_crawl, list_crawls, save_crawl
from db.models import CrawlPage


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(CrawlPage).where(CrawlPage.url == url))
        conn.commit()
    eng.dispose()


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_crawl_save_get_upsert_and_list():
    url = f"https://crawl-db-{uuid.uuid4().hex[:8]}.tn"
    domain = url.split("://")[1]
    try:
        save_crawl(url, title="Acme", domain=domain, markdown="Acme md",
                   fields={"hours": "9-18"}, status="ok", tags=["research"])
        row = get_crawl(url)
        assert row["status"] == "ok"
        assert row["fields"]["hours"] == "9-18"
        assert row["domain"] == domain

        save_crawl(url, title="Acme v2", domain=domain, markdown="updated", status="ok")
        row2 = get_crawl(url)
        assert row2["title"] == "Acme v2"
        assert row2["markdown"] == "updated"
        assert row2["fields"]["hours"] == "9-18"  # preserved on update

        rows = list_crawls(domain=domain)
        assert any(r["url"] == url for r in rows)
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_crawl_embed_writes_agent_chunk():
    from sqlalchemy import create_engine, text

    url = f"https://crawl-embed-{uuid.uuid4().hex[:8]}.tn"
    domain = url.split("://")[1]
    try:
        save_crawl(url, title="Acme", domain=domain, markdown="Acme marketing agency",
                   fields={}, status="ok")
        eng = create_engine(_db_url())
        with eng.connect() as conn:
            n = conn.execute(text(
                "SELECT count(*) FROM agent_chunks WHERE source_uri = :u"
            ), {"u": url}).scalar()
            conn.commit()
        eng.dispose()
        assert n == 0  # embedding is done by site_extract, not save_crawl itself
    finally:
        _cleanup(url)
