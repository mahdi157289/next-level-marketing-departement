"""Qualifier Agent: scores each lead against company profile after Discovery→Head."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from agents import lm_client
from knowledge.loader import company_context, qualification_criteria
from knowledge.retrieval import build_brain_context

_COMPANY = company_context()
_QUAL = qualification_criteria()

_DEFAULT_MISSION = (
    "You are the Qualifier Agent for Next Level Tech Company.\n\n"
    f"## What We Offer\n{_COMPANY}\n\n"
    f"## Scoring Criteria\n{_QUAL}\n\n"
    "Given a lead (name, URL, notes), evaluate it and respond with JSON only:\n"
    '{"score": <0-50>, "fit": "<one of: perfect|good|partial|poor>", '
    '"service_category": "<development|data|marketing|automation|migration|none>", '
    '"reasoning": "<1 sentence why>"}'
)


class QualifierAgent:
    def __init__(self, model: str | None = None):
        from config.settings import get_settings

        s = get_settings()
        self.model = model or s.agent_model_head
        self.mission = _DEFAULT_MISSION

    def qualify(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        name = lead.get("name") or lead.get("company_name") or ""
        url = lead.get("url") or ""
        notes = (lead.get("status_notes") or "")[:300]
        lead_id = lead.get("id")

        prompt = (
            f"{self.mission}\n\n"
            f"Lead name: {name}\nURL: {url}\nNotes: {notes}\n"
            "Respond JSON only."
        )
        ctx = build_brain_context("qualifier", f"{name} {url}".strip())
        if ctx:
            prompt = f"{ctx}\n\n{prompt}"
        try:
            text = lm_client.chat_completion(
                self.model,
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            parsed = self._parse_json(text)
        except Exception as e:
            parsed = {
                "score": 0,
                "fit": "poor",
                "service_category": "none",
                "reasoning": f"Qualifier LLM error: {e}",
            }

        parsed["lead_id"] = str(lead_id) if lead_id else None
        parsed["lead_name"] = name
        parsed["lead_url"] = url

        self._store_score(lead_id, parsed)

        return parsed

    @staticmethod
    def _store_score(lead_id: Any, result: Dict[str, Any]) -> None:
        if not lead_id:
            return
        try:
            from crm import service as crm_service

            score = result.get("score")
            if score is not None:
                crm_service.update_lead(str(lead_id), {"lead_score": float(score)})
        except Exception:
            pass

    def qualify_batch(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [self.qualify(l) for l in leads]

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
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
            raise ValueError("not an object")
        return data
