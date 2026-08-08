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
