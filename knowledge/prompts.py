"""File-backed system prompts (agent.md) and agent prompt resolution.

A Scout/Head agent's system prompt is resolved in priority order:
1. The DB `agent_profiles.mission_prompt` if it is non-empty and not the
   legacy bare default ("You are the Scout.").
2. The file-backed prompt at ``prompts/<agent_name>.md``.
3. A hardcoded fallback constant.

This lets operators author each agent's persona as an ``agent.md`` file in
version control, override per-deployment from the DB profile, and never fail
open if neither is present.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

_DEFAULT_DISCOVERY_PROMPT = "You are the Scout."
_DEFAULT_HEAD_PROMPT = "You are the Head Agent."

# Seeded legacy prompts (see migrations/20260714_0003_agent_profiles.py). A stock
# install has these in agent_profiles.mission_prompt; we treat them as "not
# customized" so the file-backed agent.md is authoritative by default. An
# operator override written via the UI (anything other than these strings)
# takes priority over the file.
_SEED_DEFAULTS = frozenset(
    {
        "You are the Scout.",
        "You are the Head Agent.",
        "You are the Discovery Agent for a Tunisia-based tech agency pipeline. "
        "Given web search hits (JSON with title, url, snippet), propose up to 5 "
        "plausible prospects: company/site name, primary URL, one-line fit, "
        "confidence low/med/high. Respond as Markdown bullets only.",
        "You are the Head Agent: prioritize execution for the marketing department. "
        "Given the Discovery Agent markdown and how many raw hits were retrieved, "
        "output: (1) top 3 priorities, (2) risks/blockers, (3) next concrete actions — "
        "max 12 lines, terse Markdown.",
    }
)

_PROMPT_DIR = Path(
    os.environ.get("PROMPT_DIR", Path(__file__).resolve().parents[1] / "prompts")
)


def prompt_dir() -> Path:
    return _PROMPT_DIR


def _fallback(agent_name: str) -> str:
    if agent_name == "head":
        return _DEFAULT_HEAD_PROMPT
    return _DEFAULT_DISCOVERY_PROMPT


def file_prompt(agent_name: str) -> str:
    """Read the file-backed system prompt for an agent, or '' if absent."""
    path = _PROMPT_DIR / f"{agent_name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_agent_prompt(agent_name: str, db_prompt: str | None = None) -> str:
    """Resolve the system prompt for an agent.

    Priority: file-backed agent.md (authoritative by default) -> DB override
    (only when non-empty and customized, i.e. not a seeded default) -> fallback
    constant.

    The file is the source of truth for the persona. The DB mission_prompt is an
    explicit operator override: it only wins if it has been changed away from the
    seeded default prompt.
    """
    file = file_prompt(agent_name)
    db_custom = bool(
        db_prompt and db_prompt.strip() and db_prompt.strip() not in _SEED_DEFAULTS
    )
    # Precedence: operator customization in the DB (via the SPA prompt editor)
    # overrides the file; otherwise the file-backed agent.md is authoritative;
    # finally hardcoded fallback. On a stock install the DB holds only the seeded
    # default prompt, so the file (agent.md) takes effect.
    if db_custom:
        return db_prompt
    if file:
        return file
    return _fallback(agent_name)


def scout_profile_with_prompt(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the resolved mission_prompt to a scout profile dict (non-mutating)."""
    out = dict(profile)
    out["mission_prompt"] = load_agent_prompt("discovery", profile.get("mission_prompt"))
    return out
