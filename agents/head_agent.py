"""Head / supervisor: mission planning (tool assignment) + post-discovery synthesis.

Loads mission_prompt from agent_profiles when available.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agents import lm_client
from config.settings import get_settings
from crm.client import AgentRunRecorder
from knowledge.loader import company_context
from knowledge.prompts import load_agent_prompt
from knowledge.retrieval import build_brain_context
from tools.registry import (
    catalog_for_agent,
    clamp_discovery_tools,
    tool_enabled,
)

_COMPANY = company_context()
_QUAL_CRITERIA = (
    "Lead must match one of: development (web/app/crm/admin), "
    "data (analytics/dashboards), marketing (human/AI), "
    "automation (workflows/AI agents), or migration (stack/provider). "
    "Prefer Tunisia-based or MENA region. Skip directories, news sites, and non-business pages."
)

_DEFAULT_MISSION = (
    "You are the Head Agent for Next Level Tech Company — a Tunisia-based dev shop.\n\n"
    f"## What We Offer\n{_COMPANY}\n\n"
    "Given the Discovery Agent markdown and raw hit count, "
    "output: (1) top 3 prospects worth pursuing, (2) why they fit our services, "
    "(3) risks/blockers, (4) next actions. "
    "Max 16 lines, terse Markdown."
)

_PLAN_MISSION = (
    "You are the Head Agent assigning Discovery tools for Next Level Tech Company.\n\n"
    f"## What We Offer\n{_COMPANY}\n\n"
    "Pick the best seed_query and tools. "
    "ALWAYS include web_search, llm_chat, and crm_write_leads when allowed. "
    "Add scrape or seo_audit only when page enrichment is worth the cost. "
    "Respond with JSON only (no markdown fences): "
    '{"seed_query":"...","tools":["web_search","crm_write_leads","llm_chat"],'
    '"rationale":"one short sentence"}'
)


class HeadAgent:
    def __init__(
        self,
        model: Optional[str] = None,
        *,
        mission_prompt: Optional[str] = None,
        enabled_tools: Optional[List[str]] = None,
    ) -> None:
        s = get_settings()
        profile = self._load_profile()
        self.model = model or (profile.get("model") if profile else None) or s.agent_model_head
        self.mission_prompt = (
            mission_prompt
            or load_agent_prompt("head", profile.get("mission_prompt") if profile else None)
            or _DEFAULT_MISSION
        )
        self.enabled_tools = list(
            enabled_tools
            if enabled_tools is not None
            else (profile.get("enabled_tools") if profile else None)
            or ["llm_chat"]
        )

    @staticmethod
    def _load_profile() -> Dict[str, Any]:
        try:
            from crm import service as crm_service

            return crm_service.get_agent_profile("head") or {}
        except Exception:
            return {}

    @staticmethod
    def _load_discovery_allowed() -> List[str]:
        try:
            from crm import service as crm_service

            profile = crm_service.get_agent_profile("discovery") or {}
            return list(profile.get("enabled_tools") or [])
        except Exception:
            return [t["id"] for t in catalog_for_agent("discovery")]

    def plan_discovery(
        self,
        goal: str,
        *,
        recorder: Optional[AgentRunRecorder] = None,
        allowed_tools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Assign seed_query + tools for Discovery. Records a head agent_run when recorder given."""
        allowed = allowed_tools if allowed_tools is not None else self._load_discovery_allowed()
        if not tool_enabled(self.enabled_tools, "llm_chat"):
            # Fall back without LLM
            return self._fallback_plan(goal, allowed)

        if recorder is None:
            return self._plan_core(goal, allowed)

        with recorder.agent_run(
            "head",
            model=self.model,
            input_summary=f"plan_discovery: {goal[:200]}",
        ) as run:
            run.record_api("litellm", "chat", model=self.model)
            plan = self._plan_core(goal, allowed)
            run.set_output(
                summary=(plan.get("rationale") or "")[:500],
                json={
                    "mode": "plan_discovery",
                    "seed_query": plan.get("seed_query"),
                    "tools": plan.get("tools"),
                    "skill_gaps": plan.get("skill_gaps"),
                    "rationale": plan.get("rationale"),
                },
            )
            return plan

    def _fallback_plan(self, goal: str, allowed: List[str]) -> Dict[str, Any]:
        clamped = clamp_discovery_tools(list(allowed), allowed=allowed)
        return {
            "seed_query": goal.strip(),
            "tools": clamped["tools"],
            "skill_gaps": clamped["skill_gaps"],
            "rationale": "Fallback: operator-allowed Discovery tools (Head llm_chat off or plan failed).",
            "raw": None,
        }

    def _plan_core(self, goal: str, allowed: List[str]) -> Dict[str, Any]:
        catalog_lines = "\n".join(
            f"- {t['id']}: {t['label']}" for t in catalog_for_agent("discovery") if t["id"] in set(allowed)
        )
        user_body = (
            f"{_PLAN_MISSION}\n\n"
            f"Goal / seed hint: {goal.strip()}\n\n"
            f"Allowed Discovery tools (you may only pick from these):\n{catalog_lines}\n"
        )
        ctx = build_brain_context("head", goal)
        if ctx:
            user_body = f"{ctx}\n\n{user_body}"
        if "head" in self.model.lower() or "qwen" in self.model.lower():
            user_body = "/no_think\n" + user_body
        try:
            text = lm_client.chat_completion(
                self.model,
                [{"role": "user", "content": user_body}],
                temperature=0.2,
                max_tokens=512,
            )
            parsed = _parse_plan_json(text)
            seed = (parsed.get("seed_query") or goal).strip() or goal.strip()
            requested = parsed.get("tools") or allowed
            if not isinstance(requested, list):
                requested = allowed
            clamped = clamp_discovery_tools(requested, allowed=allowed)
            return {
                "seed_query": seed,
                "tools": clamped["tools"],
                "skill_gaps": clamped["skill_gaps"],
                "rationale": str(parsed.get("rationale") or "")[:500],
                "raw": text[:2000],
            }
        except Exception:
            return self._fallback_plan(goal, allowed)

    def run(
        self,
        discovery_bundle: Dict[str, Any],
        recorder: Optional[AgentRunRecorder] = None,
    ) -> str:
        seed = discovery_bundle.get("seed_query", "")
        n = len(discovery_bundle.get("search_results") or [])

        if recorder is None:
            return self._llm_report(discovery_bundle)

        with recorder.agent_run(
            "head",
            model=self.model,
            input_summary=f"seed={seed}; hits={n}",
        ) as run:
            if not tool_enabled(self.enabled_tools, "llm_chat"):
                raise RuntimeError("llm_chat tool is disabled for Head")
            run.record_api("litellm", "chat", model=self.model)
            report = self._llm_report(discovery_bundle)
            run.set_output(
                summary=report[:500] if report else "",
                json={"raw_hits": n, "chars": len(report or ""), "mode": "synthesize"},
            )
            return report

    def _llm_report(self, discovery_bundle: Dict[str, Any]) -> str:
        seed = discovery_bundle.get("seed_query", "")
        report = discovery_bundle.get("report_markdown", "")
        n = len(discovery_bundle.get("search_results") or [])
        user_body = (
            f"{self.mission_prompt.strip()}\n\n"
            f"Seed query: {seed}\nRaw hits: {n}\n\nDiscovery report:\n{report}"
        )
        ctx = build_brain_context("head", seed)
        if ctx:
            user_body = f"{ctx}\n\n{user_body}"
        if "head" in self.model.lower() or "qwen" in self.model.lower():
            user_body = "/no_think\n" + user_body
        messages = [{"role": "user", "content": user_body}]
        return lm_client.chat_completion(self.model, messages, temperature=0.25, max_tokens=768)


def _parse_plan_json(text: str) -> Dict[str, Any]:
    """Extract JSON object from model output (plain or fenced)."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty plan")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("plan is not an object")
    return data
