"""Roster: every agent gets a dedicated page."""

from __future__ import annotations

import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from crm.agents_registry import AGENT_ROSTER, roster_entry, roster_names


def test_roster_has_all_seven_agents():
    assert roster_names() == {
        "discovery", "head", "qualifier", "categorization",
        "analysis", "outreach", "content",
    }


def test_roster_entries_are_well_formed():
    from tools.registry import _KNOWN_IDS

    assert len(AGENT_ROSTER) == 7
    seen = set()
    for entry in AGENT_ROSTER:
        assert entry["name"] not in seen
        seen.add(entry["name"])
        assert entry["display_name"]
        assert entry["description"]
        assert entry["default_tools"], "default_tools must be non-empty"
        assert set(entry["default_tools"]) <= _KNOWN_IDS
        assert entry["providers"]


def test_roster_entry_unknown_returns_none():
    assert roster_entry("nonexistent") is None


def test_llm_chat_available_to_all_roster_agents():
    from tools.registry import catalog_for_agent, validate_tool_ids

    for name in roster_names():
        ids = {t["id"] for t in catalog_for_agent(name)}
        assert "llm_chat" in ids, name
        tools = ["llm_chat"] if name != "discovery" else ["llm_chat", "web_search"]
        assert validate_tool_ids(tools, agent_name=name) == tools


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_agent_profiles_list_includes_roster(client):
    from crm import service

    names = {p["agent_name"] for p in service.list_agent_profiles()}
    assert roster_names() <= names


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_get_agent_profile_falls_back_to_roster():
    from crm import service

    p = service.get_agent_profile("categorization")
    assert p is not None
    assert p["display_name"] == "Categorization"
    assert p["enabled_tools"] == ["llm_chat"]
    assert p["mission_prompt"] is None


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_get_agent_profile_unknown_returns_none():
    from crm import service

    assert service.get_agent_profile("nonexistent") is None


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_patch_qualifier_upserts_row(client):
    from crm import service

    r = client.patch(
        "/api/agents/qualifier",
        json={"display_name": "Qualifier 2.0", "mission_prompt": "Score leads"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent_name"] == "qualifier"
    assert body["display_name"] == "Qualifier 2.0"
    assert body["mission_prompt"] == "Score leads"
    row = service.get_agent_profile("qualifier")
    assert row is not None
    assert row["display_name"] == "Qualifier 2.0"
