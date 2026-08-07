"""Unit tests for file-backed agent prompts (agent.md resolution)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from knowledge import prompts


def test_db_prompt_takes_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMPT_DIR", str(tmp_path))
    (tmp_path / "discovery.md").write_text("FROM FILE", encoding="utf-8")
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    assert prompts.load_agent_prompt("discovery", "I am the Scout, obey these rules.") == "I am the Scout, obey these rules."


def test_legacy_bearer_default_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    (tmp_path / "discovery.md").write_text("FROM FILE", encoding="utf-8")
    assert prompts.load_agent_prompt("discovery", "You are the Scout.") == "FROM FILE"


def test_empty_db_prompt_uses_file(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    (tmp_path / "head.md").write_text("FROM FILE", encoding="utf-8")
    assert prompts.load_agent_prompt("head", "") == "FROM FILE"
    assert prompts.load_agent_prompt("head", None) == "FROM FILE"


def test_missing_file_and_db_uses_fallback_constant(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    assert prompts.load_agent_prompt("discovery", "") == "You are the Scout."
    assert prompts.load_agent_prompt("head", None) == "You are the Head Agent."


def test_file_prompt_returns_empty_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    assert prompts.file_prompt("nope") == ""


def test_scout_profile_with_prompt_resolves(monkeypatch, tmp_path):
    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    (tmp_path / "discovery.md").write_text("SYSTEM FROM FILE", encoding="utf-8")
    profile = {"model": "m", "mission_prompt": "", "enabled_tools": ["web_search"]}
    out = prompts.scout_profile_with_prompt(profile)
    assert out["mission_prompt"] == "SYSTEM FROM FILE"
    assert out is not profile  # non-mutating
    assert profile["mission_prompt"] == ""
