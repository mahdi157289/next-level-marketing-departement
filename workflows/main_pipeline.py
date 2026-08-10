"""Minimal multi-agent pipeline (Discovery → Head → Qualifier).

Discovery: finds leads via web search
Head: synthesizes and prioritizes
Qualifier: scores each lead against company profile
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.discovery_agent import DiscoveryAgent
from agents.head_agent import HeadAgent
from agents.qualifier_agent import QualifierAgent
from crm.client import AgentRunRecorder


def run_minimal_marketing_pipeline(
    seed_query: str,
    *,
    max_search_results: Optional[int] = None,
    recorder: Optional[AgentRunRecorder] = None,
    trigger: str = "cli",
) -> Dict[str, Any]:
    """Run Discovery → Head → Qualifier. Opens/closes a CRM pipeline_run."""
    if recorder is None:
        recorder = AgentRunRecorder(trigger=trigger, seed_query=seed_query)

    recorder.start_pipeline()
    try:
        discovery = DiscoveryAgent().run(
            seed_query,
            max_results=max_search_results,
            recorder=recorder,
        )
        head_report = HeadAgent().run(discovery, recorder=recorder)

        lead_ids = discovery.get("lead_ids") or []
        if lead_ids:
            try:
                from workflows.enrich_leads import enrich_leads

                enrich_leads(lead_ids, recorder=recorder)
            except Exception:
                pass

        qualifier = QualifierAgent()
        qualifications = []
        for lid in lead_ids:
            try:
                from crm import service as crm_service

                lead = crm_service.get_lead(lid)
                if lead:
                    q = qualifier.qualify(lead)
                    qualifications.append(q)
            except Exception:
                pass

        recorder.complete_pipeline("success")
        return {
            "seed_query": seed_query,
            "pipeline_run_id": recorder.pipeline_run_id,
            "status": "success",
            "discovery": discovery,
            "head_report_markdown": head_report,
            "qualifications": qualifications,
        }
    except Exception as exc:
        recorder.complete_pipeline("failed", meta={"error": str(exc)})
        return {
            "seed_query": seed_query,
            "pipeline_run_id": recorder.pipeline_run_id,
            "status": "failed",
            "error": str(exc),
            "discovery": None,
            "head_report_markdown": None,
            "qualifications": [],
        }
