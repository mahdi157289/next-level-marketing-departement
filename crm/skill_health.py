"""Real live checks for each skill in the tools catalog (green/red/amber lamps).

Each check calls the *real* tool with a tiny probe (no mocks) and returns a
verdict dict. `run_skill_checks` executes all checks in parallel with per-skill
time budgets so one slow or broken skill never blocks the others.

Verdict statuses:
    ok    - the probe succeeded (green)
    fail  - the probe ran and failed, or timed out (red)
    skip  - cannot test (missing key / dependency) (amber)
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text

from config.settings import get_settings
from db.session import engine
from tools.registry import TOOL_CATALOG


def _ok(detail: str) -> Dict[str, str]:
    return {"status": "ok", "detail": detail}


def _fail(detail: str) -> Dict[str, str]:
    return {"status": "fail", "detail": detail}


def _skip(detail: str) -> Dict[str, str]:
    return {"status": "skip", "detail": detail}


def check_web_search() -> Dict[str, str]:
    from tools.web_search_tool import get_last_web_search_diag, web_search_tool

    try:
        results = web_search_tool("Next Level Tech Company Tunisia web development", max_results=2)
    except Exception as e:  # noqa: BLE001 - probe must never raise
        return _fail(f"{type(e).__name__}: {e}")
    if not results:
        return _fail(f"no results — network or DDG blocked. diag: {get_last_web_search_diag()}")
    first = (results[0].get("url") or "").strip()
    return _ok(f"{len(results)} result(s); first: {first[:80]}")


def check_llm_chat() -> Dict[str, str]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(
        base_url=s.openai_base_url(),
        api_key=s.openai_api_key,
        timeout=20.0,
        max_retries=0,
    )
    try:
        r = client.chat.completions.create(
            model=s.agent_model_head,
            messages=[{"role": "user", "content": "Reply with one word only: OK"}],
            temperature=0.2,
            max_tokens=8,
        )
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    text_out = (getattr(r.choices[0].message, "content", None) or "").strip()
    if not text_out:
        return _fail(f"empty completion from model {s.agent_model_head!r}")
    return _ok(f"model {s.agent_model_head!r} replied: {text_out[:40]}")


def check_seo_audit() -> Dict[str, str]:
    from tools.seo_audit_tool import seo_audit_tool

    try:
        out = seo_audit_tool("https://example.com/")
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    score = out.get("seo_score") if isinstance(out, dict) else None
    if score is None:
        return _fail(f"no seo_score: {str(out)[:160]}")
    return _ok(f"seo_score={score} issues={out.get('issues')}")


def check_scrape() -> Dict[str, str]:
    from tools.scrape_tool import scrape_tool

    try:
        out = scrape_tool("https://example.com/")
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    if not isinstance(out, dict):
        return _fail(f"unexpected result: {str(out)[:160]}")
    if out.get("error"):
        return _fail(str(out["error"])[:160])
    title = out.get("title") or ""
    return _ok(f"title={str(title)[:60]!r}")


def check_crm_write_leads() -> Dict[str, str]:
    """Probe-write one lead through the real CRM path, read it back, then delete."""
    from tools.crm_tool import crm_write_tool

    marker = uuid.uuid4().hex[:10]
    url = f"https://healthcheck.local/{marker}"
    lead_id: Optional[str] = None
    try:
        result = crm_write_tool("leads", {"name": f"PROBE {marker}", "url": url, "source": "skill_health"})
        lead_id = result.split(":", 1)[1]
        with engine.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM leads WHERE url = :url"), {"url": url}).scalar_one()
        if int(n) < 1:
            return _fail(f"write returned ok but read-back found 0 rows (id={lead_id})")
        return _ok(f"wrote + read back lead {lead_id}")
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    finally:
        if lead_id:
            try:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM leads WHERE id = :id"), {"id": lead_id})
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


def check_meta_ads_search() -> Dict[str, str]:
    token = (get_settings().meta_ads_access_token or "").strip()
    if not token:
        return _skip("META_ADS_ACCESS_TOKEN not set")
    from tools.meta_ads_tool import meta_ads_search

    try:
        results = meta_ads_search("web agency", country="TN", limit=2)
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    if not results:
        return _fail("query returned 0 results")
    first = (results[0].get("title") or results[0].get("url") or "")
    return _ok(f"{len(results)} ad page(s); first: {str(first)[:80]}")


def check_google_maps_search() -> Dict[str, str]:
    from tools.google_maps_tool import _SUPERLEADFINDER_PATH, get_last_google_maps_diag, google_maps_search

    if not _SUPERLEADFINDER_PATH or not _SUPERLEADFINDER_PATH.strip():
        return _skip("Google Maps Node scraper not configured")
    try:
        results = google_maps_search("software agency", region="Tunis", max_results=1)
    except Exception as e:  # noqa: BLE001
        return _fail(f"{type(e).__name__}: {e}")
    if not results:
        return _fail(f"0 results. diag: {get_last_google_maps_diag()}")
    first = results[0].get("title") or results[0].get("name") or ""
    return _ok(f"{len(results)} place(s); first: {str(first)[:80]}")


# skill_id -> check function
SKILL_CHECKS: Dict[str, Callable[[], Dict[str, str]]] = {
    "web_search": check_web_search,
    "llm_chat": check_llm_chat,
    "seo_audit": check_seo_audit,
    "scrape": check_scrape,
    "crm_write_leads": check_crm_write_leads,
    "meta_ads_search": check_meta_ads_search,
    "google_maps_search": check_google_maps_search,
}

# per-skill wall-clock budget in seconds
TIME_BUDGETS: Dict[str, float] = {
    "web_search": 15.0,
    "llm_chat": 25.0,
    "seo_audit": 20.0,
    "scrape": 25.0,
    "crm_write_leads": 10.0,
    "meta_ads_search": 15.0,
    "google_maps_search": 30.0,
}


def _run_checked(fn: Callable[[], Any]) -> tuple[Dict[str, str], float]:
    """Run one check function, timing it; a raising check becomes a fail verdict."""
    t0 = time.monotonic()
    try:
        out = fn()
        if not isinstance(out, dict):
            out = {"status": "fail", "detail": f"check returned non-dict: {type(out).__name__}"}
        out.setdefault("status", "fail")
        out.setdefault("detail", "")
    except Exception as e:  # noqa: BLE001
        out = {"status": "fail", "detail": f"{type(e).__name__}: {e}"}
    return out, (time.monotonic() - t0) * 1000.0


def run_skill_checks(
    checkers: Optional[Dict[str, Callable[[], Any]]] = None,
    budgets: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Run all skill checks in parallel; return verdicts ordered like the catalog.

    Testability: `checkers` / `budgets` can be injected (defaults are the real
    registry). A check that exceeds its budget is reported as a timeout (fail).
    """
    checkers = checkers if checkers is not None else SKILL_CHECKS
    budgets = budgets if budgets is not None else TIME_BUDGETS
    results: Dict[str, Dict[str, Any]] = {}
    if not checkers:
        return []

    with ThreadPoolExecutor(max_workers=len(checkers)) as ex:
        future_map = {ex.submit(_run_checked, fn): sid for sid, fn in checkers.items()}
        for fut, sid in future_map.items():
            budget = budgets.get(sid, 20.0)
            try:
                verdict, latency_ms = fut.result(timeout=budget)
            except TimeoutError:
                verdict = {"status": "fail", "detail": f"timed out after {budget:.0f}s"}
                latency_ms = budget * 1000.0
            results[sid] = {
                "skill_id": sid,
                "status": verdict.get("status", "fail"),
                "detail": verdict.get("detail", ""),
                "latency_ms": int(latency_ms),
            }

    order = [t["id"] for t in TOOL_CATALOG if t["id"] in checkers]
    ordered = [results[sid] for sid in order]
    ordered += [v for k, v in results.items() if k not in order]
    return ordered
