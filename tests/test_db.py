import os
import uuid
from typing import Optional

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import sessionmaker

from db.models import Lead, LeadStatus


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def engine():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL not set")
    eng = create_engine(url, pool_pre_ping=True)
    return eng


def test_database_connect(engine):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def test_lead_insert_and_read(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    unique = str(uuid.uuid4())[:8]
    url = f"https://test-{unique}.example.com"
    try:
        lead = Lead(name=f"Test Co {unique}", url=url, status=LeadStatus.raw)
        session.add(lead)
        session.commit()
        found = session.scalars(select(Lead).where(Lead.name == f"Test Co {unique}")).first()
        assert found is not None
        assert found.status == LeadStatus.raw
    finally:
        session.execute(delete(Lead).where(Lead.url == url))
        session.commit()
        session.close()
