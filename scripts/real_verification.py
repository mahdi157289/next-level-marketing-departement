"""
Run REAL checks (no mocks) — CRM, DuckDuckGo, LM Studio.

Usage (from project root, PowerShell examples):

  # 1) Database + CRM roundtrip (uses DATABASE_URL)
  python scripts/real_verification.py --crm

  # 2) Live web search (internet + ddgs)
  python scripts/real_verification.py --search

  # 2b) SEO (httpx + bs4) and scrape (Playwright — run: playwright install chromium)
  python scripts/real_verification.py --seo
  python scripts/real_verification.py --scrape

  # 3) LM Studio — load ONE model first in LM Studio, then pass exact id:
  python scripts/real_verification.py --lm-studio phi-2

  # Everything you can run offline except search/LM needs network/server
  python scripts/real_verification.py --all

  # 4) Minimal agent pipeline (real DuckDuckGo + LM Studio chat via OpenAI SDK)
  #    Match AGENT_MODEL_* to models loaded in LM Studio (or set in .env).
  python scripts/real_verification.py --pipeline
  python scripts/real_verification.py --pipeline --pipeline-query "Next Level Tunisia web agency"

  # 5) Docker full smoke (from inside app container):
  python scripts/real_verification.py --docker-smoke
  python scripts/real_verification.py --docker-smoke --skip-llm   # Phase A — no LM Studio

Manual intervention checklist:
  - Postgres: docker compose up -d postgres redis litellm app
  - LM Studio: Local Server ON at http://127.0.0.1:1234 ; load models before LLM steps
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Ensure project root on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.crm_tool import crm_read_tool
from tools.scrape_tool import scrape_tool
from tools.seo_audit_tool import seo_audit_tool
from tools.web_search_tool import get_last_web_search_diag, web_search_tool
from workflows.main_pipeline import run_minimal_marketing_pipeline


def verify_crm() -> bool:
    """Read-only CRM connectivity check — does not insert fake leads."""
    url_env = os.getenv("DATABASE_URL")
    if not url_env:
        print("SKIP CRM: DATABASE_URL not set.")
        return False
    try:
        rows = crm_read_tool(limit=50)
    except Exception as e:
        print(f"FAIL CRM read: {e}")
        return False
    discovery = [r for r in rows if (r.get("source") or "") == "discovery"]
    print(f"CRM read OK: {len(rows)} lead(s) visible, {len(discovery)} discovery-sourced")
    if discovery:
        sample = discovery[0]
        print(f"   Sample discovery: {(sample.get('name') or '')[:60]} → {sample.get('url')}")
    else:
        print("   (no discovery leads yet — run --pipeline for real extraction)")
    return True


def verify_search() -> bool:
    print("Calling DuckDuckGo (live)...")
    results = web_search_tool("software agency Tunisia tech", max_results=4)
    if not results:
        print("FAIL: no search results — network or DDG blocked.")
        print(f"Diag: {get_last_web_search_diag()}")
        print("Tip: pip install -U ddgs   (replaces deprecated duckduckgo-search)")
        return False
    print(f"OK: {len(results)} result(s). First URL: {results[0].get('url','')}")
    print(f"   Title: {(results[0].get('title') or '')[:80]}...")
    return True


def verify_seo() -> bool:
    print("SEO audit https://example.com/ (live)...")
    out = seo_audit_tool("https://example.com/")
    score = out.get("seo_score")
    if score is None:
        print(f"FAIL: {out}")
        return False
    print(f"OK seo_score={score} load_time_s={out.get('load_time_s')} issues={out.get('issues')}")
    return True


def verify_scrape() -> bool:
    print("Playwright scrape https://example.com/ (live)...")
    out = scrape_tool("https://example.com/")
    if out.get("error"):
        print(f"FAIL: {out}")
        print("Tip: playwright install chromium")
        return False
    print(f"OK title={out.get('title')!r}")
    return True


def verify_pipeline(seed_query: str | None = None) -> bool:
    q = (seed_query or os.getenv("PIPELINE_SEED_QUERY") or "software agency Tunisia").strip()
    print(f"Minimal pipeline (Discovery → Head), seed={q!r}...")
    try:
        out = run_minimal_marketing_pipeline(q, max_search_results=3, trigger="cli")
    except Exception as e:
        print(f"FAIL pipeline error: {e}")
        return False
    pid = out.get("pipeline_run_id")
    status = out.get("status")
    print(f"CRM pipeline_run_id={pid} status={status}")
    if status == "failed":
        print(f"FAIL pipeline status failed: {out.get('error')}")
        return False
    discovery = out.get("discovery") or {}
    n = len(discovery.get("search_results") or [])
    head = (out.get("head_report_markdown") or "").strip()
    disc = (discovery.get("report_markdown") or "").strip()
    leads = discovery.get("lead_ids") or []
    print(f"OK search_hits={n} discovery_chars={len(disc)} head_chars={len(head)} leads_written={len(leads)}")
    if n < 1 or not disc or not head:
        print("FAIL incomplete pipeline output.")
        return False
    return True


def verify_litellm_health() -> bool:
    base = (os.getenv("LITELLM_BASE_URL") or "http://litellm:4000").rstrip("/")
    url = f"{base}/health"
    print(f"LiteLLM GET {url}")
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'dev-key')}"})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            if resp.status != 200:
                print(f"FAIL health status {resp.status}")
                return False
    except urllib.error.URLError as e:
        print(f"FAIL reach LiteLLM: {e}")
        return False
    print("OK LiteLLM health")
    return True


def verify_litellm_chat(model: str) -> bool:
    """Chat via OPENAI_API_BASE (LiteLLM proxy) using model alias."""
    api_base = (os.getenv("OPENAI_API_BASE") or os.getenv("LITELLM_BASE_URL", "http://litellm:4000") + "/v1").rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "dev-key")
    url = f"{api_base}/chat/completions"
    is_head = "head" in model.lower() or model == "head-model"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "/no_think Reply with one word only: OK" if is_head else "Reply with one word only: OK",
            }
        ],
        "temperature": 0.2,
        "max_tokens": 128 if is_head else 24,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    print(f"LiteLLM POST {url} model={model!r}")
    try:
        with urllib.request.urlopen(req, timeout=300.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
        print("Tip: start LM Studio Local Server and load the model behind this LiteLLM alias.")
        return False
    except urllib.error.URLError as e:
        print(f"FAIL reach LiteLLM: {e}")
        return False
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    txt = msg.get("content") or msg.get("reasoning_content") or ""
    print(f"OK completion: {str(txt).strip()[:120]!r}")
    return bool(str(txt).strip())


def verify_crewai_import() -> bool:
    try:
        import crewai  # noqa: F401

        print("OK crewai import (Python 3.11+ image)")
        return True
    except ImportError as e:
        print(f"FAIL crewai import: {e}")
        return False


def run_docker_smoke(*, skip_llm: bool = False) -> bool:
    """Ordered smoke: tools (no LLM) then LiteLLM + pipeline (LM Studio required)."""
    ok = True
    print("=== Docker smoke Phase A (no LM Studio) ===")
    ok = verify_crewai_import() and ok
    ok = verify_crm() and ok
    ok = verify_search() and ok
    ok = verify_seo() and ok
    ok = verify_scrape() and ok
    ok = verify_litellm_health() and ok

    if skip_llm:
        print("\n--- Phase A complete (--skip-llm); start LM Studio for Phase B ---")
        return ok

    print("\n" + "=" * 60)
    print(">>> START LM STUDIO NOW <<<")
    print("  1) Load models for aliases: light-model (phi-2), discovery-model, head-model")
    print("  2) Local Server ON at http://127.0.0.1:1234")
    print("=" * 60 + "\n")

    print("=== Docker smoke Phase B (LM Studio + LiteLLM) ===")
    chat_model = os.getenv("DOCKER_SMOKE_CHAT_MODEL", "light-model")
    ok = verify_litellm_chat(chat_model) and ok
    ok = verify_pipeline() and ok
    return ok


def verify_lm_studio(model: str, base: str | None = None) -> bool:
    # Prefer LiteLLM when OPENAI_API_BASE is set (Docker app container).
    if os.getenv("OPENAI_API_BASE"):
        return verify_litellm_chat(model)
    base = (base or os.getenv("LM_STUDIO_BASE", "http://127.0.0.1:1234")).rstrip("/")
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with one word only: OK"}],
        "temperature": 0.2,
        "max_tokens": 24,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    print(f"LM Studio POST {url} model={model!r}")
    try:
        with urllib.request.urlopen(req, timeout=300.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:400]}")
        return False
    except urllib.error.URLError as e:
        print(f"FAIL reach server: {e}")
        return False
    txt = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    print(f"OK completion: {str(txt).strip()[:120]!r}")
    return bool(str(txt).strip())


def main() -> int:
    p = argparse.ArgumentParser(description="Real verification (no mocks)")
    p.add_argument("--crm", action="store_true")
    p.add_argument("--search", action="store_true")
    p.add_argument("--lm-studio", metavar="MODEL_ID", help="Exact LM Studio model id, e.g. phi-2")
    p.add_argument("--lm-base", default=os.getenv("LM_STUDIO_BASE", "http://127.0.0.1:1234"))
    p.add_argument("--seo", action="store_true", help="Live SEO audit on example.com")
    p.add_argument("--scrape", action="store_true", help="Live Playwright scrape on example.com")
    p.add_argument("--pipeline", action="store_true", help="Discovery→Head pipeline (DDG + LM Studio)")
    p.add_argument("--pipeline-query", dest="pipeline_query", default=None, help="Seed for --pipeline")
    p.add_argument("--all", action="store_true", help="CRM + search + seo + scrape (no LM unless --lm-studio)")
    p.add_argument(
        "--docker-smoke",
        action="store_true",
        help="Full ordered smoke for app container (tools then LiteLLM pipeline)",
    )
    p.add_argument(
        "--skip-llm",
        action="store_true",
        help="With --docker-smoke: Phase A only (no LM Studio chat/pipeline)",
    )
    args = p.parse_args()

    if not any(
        [
            args.crm,
            args.search,
            args.seo,
            args.scrape,
            args.pipeline,
            args.lm_studio,
            args.all,
            args.docker_smoke,
        ]
    ):
        p.print_help()
        return 2

    ok = True

    if args.docker_smoke:
        ok = run_docker_smoke(skip_llm=args.skip_llm) and ok
        print("\n--- Summary ---")
        print("PASSED all requested checks." if ok else "One or more checks FAILED or SKIPPED.")
        return 0 if ok else 1

    if args.crm or args.all:
        ok = verify_crm() and ok

    if args.search or args.all:
        ok = verify_search() and ok

    if args.seo or args.all:
        ok = verify_seo() and ok

    if args.scrape or args.all:
        ok = verify_scrape() and ok

    if args.pipeline:
        ok = verify_pipeline(seed_query=args.pipeline_query) and ok

    if args.lm_studio:
        ok = verify_lm_studio(args.lm_studio, base=args.lm_base) and ok

    print("\n--- Summary ---")
    print("PASSED all requested checks." if ok else "One or more checks FAILED or SKIPPED.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
