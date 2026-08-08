"""Discovery-style reasoning over DuckDuckGo results + LM Studio.

Loads mission_prompt + enabled_tools from agent_profiles when available.
Supports cooperative cancel via should_cancel callable.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from agents import lm_client
from agents.memory import build_lesson_summary
from config.settings import get_settings
from crm.client import AgentRunRecorder, CancelledError
from knowledge.loader import company_context
from knowledge.retrieval import build_brain_context
from tools.registry import resolve_callable, tool_enabled
from tools.web_search_tool import web_search_tool

# Defense in depth — web_search_tool already ranks/filters; keep CRM write clean.
_JUNK_HOST_NEEDLES = (
    "drive.google.com",
    "accounts.google.com",
    "docs.google.com",
    "support.microsoft.com",
    "login.microsoftonline.com",
    "outlook.live.com",
    "softonic.com",
    "microsoft.com",
    "wikipedia.org",
    "wiktionary.org",
    "britannica.com",
    "merriam-webster.com",
    "cambridge.org",
    "dictionary.com",
    "bing.com",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "medium.com",
    "news.ycombinator.com",
    "blogspot.com",
    "wordpress.com",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "pinterest.com",
)

_COMPANY = company_context()

def _default_mission() -> str:
    lessons = build_lesson_summary()
    return (
        "You are the Discovery Agent for Next Level Tech Company — a Tunisia-based dev shop. "
        "Your job: find real businesses that need our services.\n\n"
        f"## What We Offer\n{_COMPANY}\n\n"
        f"## Past Lessons (learn from previous runs)\n{lessons}\n\n"
        "Given web search hits (JSON with title, url, snippet), propose up to 5 REAL BUSINESS prospects: "
        "company name, primary URL, one-line fit, confidence low/med/high. "
        "REQUIREMENTS:\n"
        "- Only list actual companies or organizations that could buy our services\n"
        "- Skip directories, blog posts, news articles, YouTube videos, social media, Wikipedia\n"
        "- Skip educational content, tutorials, forum discussions\n"
        "- Skip other software/development agencies (they are competitors, not clients)\n"
        "- GOOD leads: e-commerce, retail, services, real estate, education, logistics — any business\n"
        "  running ads or needing a better website, app, CRM, automation, or AI marketing\n"
        "- A good lead has a company name and is clearly a business needing our services\n"
        "- When in doubt, leave it out\n"
        "Respond as Markdown bullets only."
    )


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def filter_prospect_hits(hits: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Drop obvious non-prospect URLs before CRM write."""
    kept: List[Dict[str, str]] = []
    for hit in hits:
        url = (hit.get("url") or "").strip()
        host = _host(url)
        if not url or not host:
            continue
        if any(n in host or n in url.lower() for n in _JUNK_HOST_NEEDLES):
            continue
        kept.append(hit)
    return kept


class DiscoveryAgent:
    def __init__(
        self,
        model: Optional[str] = None,
        *,
        mission_prompt: Optional[str] = None,
        enabled_tools: Optional[List[str]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> None:
        s = get_settings()
        profile = self._load_profile()
        self.model = model or (profile.get("model") if profile else None) or s.agent_model_discovery
        self.mission_prompt = (
            mission_prompt
            or (profile.get("mission_prompt") if profile else None)
            or _default_mission()
        )
        self.enabled_tools = list(
            enabled_tools
            if enabled_tools is not None
            else (profile.get("enabled_tools") if profile else None)
            or ["meta_ads_search", "google_maps_search", "web_search",
                "crm_write_leads", "llm_chat"]
        )
        self.should_cancel = should_cancel or (lambda: False)

    @staticmethod
    def _load_profile() -> Dict[str, Any]:
        try:
            from crm import service as crm_service

            return crm_service.get_agent_profile("discovery") or {}
        except Exception:
            return {}

    def _check_cancel(self) -> None:
        if self.should_cancel():
            raise CancelledError("Discovery cancelled by operator (Finish)")

    def run(
        self,
        seed_query: str,
        max_results: int = 5,
        recorder: Optional[AgentRunRecorder] = None,
    ) -> Dict[str, Any]:
        if recorder is None:
            return self._run_core(seed_query, max_results)

        with recorder.agent_run(
            "discovery",
            model=self.model,
            input_summary=seed_query,
        ) as run:
            self._check_cancel()

            if not tool_enabled(self.enabled_tools, "web_search"):
                raise RuntimeError("web_search tool is disabled for Discovery")

            raw: List[Dict[str, str]] = []

            # 1) Meta Ad Library — businesses already spending on ads (hot leads)
            if tool_enabled(self.enabled_tools, "meta_ads_search"):
                run.record_api("meta", "ads_search")
                meta_fn = resolve_callable("meta_ads_search")
                if meta_fn:
                    try:
                        raw = meta_fn(
                            search_terms=seed_query,
                            country="TN",
                            limit=max_results,
                        )
                    except Exception as e:
                        raw = []

            # 2) Google Maps — local businesses with real addresses/phones/ratings
            if len(raw) < max_results and tool_enabled(self.enabled_tools, "google_maps_search"):
                run.record_api("playwright", "google_maps")
                gm_fn = resolve_callable("google_maps_search")
                if gm_fn:
                    gm_hits = filter_prospect_hits(
                        gm_fn(seed_query, region="Tunisia", max_results=max(max_results, 10))
                    )
                    existing_urls = {r.get("url") for r in raw}
                    for hit in gm_hits:
                        if hit.get("url") not in existing_urls:
                            raw.append(hit)
                    raw = raw[:max_results]

            # 3) DuckDuckGo fallback — general web search
            if len(raw) < max_results and tool_enabled(self.enabled_tools, "web_search"):
                run.record_api("ddgs", "web_search")
                search_fn = resolve_callable("web_search") or web_search_tool
                extra = filter_prospect_hits(
                    search_fn(seed_query, max_results=max(max_results * 3, 10))
                )
                existing_urls = {r.get("url") for r in raw}
                for hit in extra:
                    if hit.get("url") not in existing_urls:
                        raw.append(hit)
                raw = raw[:max_results]
            self._check_cancel()

            lead_ids: List[str] = []
            if tool_enabled(self.enabled_tools, "crm_write_leads"):
                for hit in raw:
                    self._check_cancel()
                    lead = recorder.create_lead_from_hit(hit, agent_run_id=run.id)
                    if lead and lead.get("id") and lead.get("created"):
                        lead_ids.append(str(lead["id"]))
                        run.increment_records()

            # Optional enrichments (best-effort; skip on failure)
            enrichments: List[Dict[str, Any]] = []
            if tool_enabled(self.enabled_tools, "seo_audit") and raw:
                seo_fn = resolve_callable("seo_audit")
                if seo_fn:
                    try:
                        run.record_api("seo_audit", "audit")
                        enrichments.append({"seo": seo_fn(raw[0]["url"])})
                    except Exception as e:
                        enrichments.append({"seo_error": str(e)})
            if tool_enabled(self.enabled_tools, "scrape") and raw:
                scrape_fn = resolve_callable("scrape")
                if scrape_fn:
                    try:
                        run.record_api("scrape", "page")
                        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

                        with ThreadPoolExecutor(max_workers=1) as pool:
                            fut = pool.submit(scrape_fn, raw[0]["url"])
                            enrichments.append({"scrape": fut.result(timeout=25)})
                    except FuturesTimeout:
                        enrichments.append({"scrape_error": "timeout after 25s"})
                    except Exception as e:
                        enrichments.append({"scrape_error": str(e)})

            self._check_cancel()
            if not tool_enabled(self.enabled_tools, "llm_chat"):
                raise RuntimeError("llm_chat tool is disabled for Discovery")

            run.record_api("litellm", "chat", model=self.model)
            report = self._llm_report(seed_query, raw)
            out_json: Dict[str, Any] = {
                "search_hits": len(raw),
                "leads_written": len(lead_ids),
                "lead_ids": lead_ids,
                "enabled_tools": self.enabled_tools,
            }
            if enrichments:
                out_json["enrichments"] = enrichments
            run.set_output(
                summary=report[:500] if report else "",
                json=out_json,
            )
            return {
                "seed_query": seed_query,
                "search_results": raw,
                "report_markdown": report,
                "lead_ids": lead_ids,
            }

    def _run_core(self, seed_query: str, max_results: int) -> Dict[str, Any]:
        self._check_cancel()
        raw: List[Dict[str, str]] = []
        if tool_enabled(self.enabled_tools, "meta_ads_search"):
            meta_fn = resolve_callable("meta_ads_search")
            if meta_fn:
                try:
                    raw = meta_fn(search_terms=seed_query, country="TN", limit=max_results)
                except Exception:
                    raw = []
        # Google Maps — local businesses
        if len(raw) < max_results and tool_enabled(self.enabled_tools, "google_maps_search"):
            gm_fn = resolve_callable("google_maps_search")
            if gm_fn:
                gm_hits = filter_prospect_hits(
                    gm_fn(seed_query, region="Tunisia", max_results=max(max_results, 10))
                )
                existing_urls = {r.get("url") for r in raw}
                for hit in gm_hits:
                    if hit.get("url") not in existing_urls:
                        raw.append(hit)
                raw = raw[:max_results]
        if len(raw) < max_results and tool_enabled(self.enabled_tools, "web_search"):
            search_fn = resolve_callable("web_search") or web_search_tool
            extra = filter_prospect_hits(
                search_fn(seed_query, max_results=max(max_results * 3, 10))
            )
            existing_urls = {r.get("url") for r in raw}
            for hit in extra:
                if hit.get("url") not in existing_urls:
                    raw.append(hit)
            raw = raw[:max_results]
        self._check_cancel()
        report = self._llm_report(seed_query, raw) if tool_enabled(self.enabled_tools, "llm_chat") else ""
        return {"seed_query": seed_query, "search_results": raw, "report_markdown": report}

    def _llm_report(self, seed_query: str, raw: list) -> str:
        """Ask Discovery model for a short prospect list.

        LM Studio errors with 'Context size has been exceeded' when
        prompt_tokens + max_tokens > n_ctx. Shrink both on retry; if all LLM
        attempts fail, return a deterministic report so the scout can still succeed.
        """
        mission = (self.mission_prompt or "").strip()
        if len(mission) > 1000:
            mission = mission[:1000] + "…"

        ctx = build_brain_context("discovery", seed_query)
        if ctx:
            mission = f"{mission}\n\n{ctx}"

        def _build(max_hits: int, title_n: int, snip_n: int, blob_cap: int) -> str:
            slim = []
            for hit in raw[:max_hits]:
                slim.append(
                    {
                        "title": (hit.get("title") or "")[:title_n],
                        "url": (hit.get("url") or "")[:160],
                        "snippet": (hit.get("snippet") or "")[:snip_n],
                    }
                )
            blob = json.dumps(slim, ensure_ascii=False)
            if len(blob) > blob_cap:
                blob = blob[:blob_cap] + "…"
            return (
                "List up to 5 prospects as Markdown bullets: name, URL, fit, confidence.\n"
                f"{mission}\nSeed: {seed_query}\nHits JSON:\n{blob}"
            )

        def _fallback_report() -> str:
            lines = [f"*Deterministic report (LLM context exceeded). Seed: `{seed_query}`*"]
            for hit in raw[:5]:
                title = (hit.get("title") or hit.get("url") or "hit")[:120]
                url = hit.get("url") or ""
                lines.append(f"* **{title}** — {url} — fit: search hit — confidence: med")
            if not raw:
                lines.append("* No search hits to report.")
            return "\n".join(lines)

        # (hits, title, snip, blob_cap, max_tokens)
        attempts = (
            (4, 80, 100, 1600, 192),
            (2, 60, 60, 700, 96),
            (1, 40, 40, 350, 64),
        )
        last_err: Optional[BaseException] = None
        for max_hits, title_n, snip_n, blob_cap, max_tok in attempts:
            content = _build(max_hits, title_n, snip_n, blob_cap)
            try:
                return lm_client.chat_completion(
                    self.model,
                    [{"role": "user", "content": content}],
                    temperature=0.35,
                    max_tokens=max_tok,
                )
            except BaseException as e:
                last_err = e
                msg = str(e).lower()
                if "context" in msg or "400" in msg:
                    continue
                # Non-context errors: still fall back so scout leads are not wasted
                break
        # Do not fail the scout — leads + search already happened.
        note = f" (llm_error={type(last_err).__name__}: {str(last_err)[:120]})" if last_err else ""
        return _fallback_report() + f"\n\n_Note: LLM report degraded{note}_"
