"""Real integration tests — no mocks. Run only when you intentionally enable them.

Prerequisites:
  DATABASE_URL — for CRM tests in test_tools.py (already real)

  Live DuckDuckGo:
    RUN_LIVE_TESTS=1

  Live LM Studio chat:
    RUN_LIVE_TESTS=1
    LM_STUDIO_BASE=http://127.0.0.1:1234   (optional)
    LM_VERIFY_MODEL=phi-2                   (exact id as in LM Studio; load this model first)

  Live minimal pipeline (DDG + dual LLM calls):
    RUN_LIVE_TESTS=1
    LM_VERIFY_MODEL=<same id loaded in LM Studio>   (also sets AGENT_MODEL_* via test)

Recommended model for a quick LM check: phi-2 (small / fast).
For supervisor-style behaviour later: qwen/qwen3-14b (heavy — load explicitly).

LM Studio note: many models’ prompt templates reject `system` messages — agent code uses **user**-only chat payloads so Mistral/Gemma/etc. accept completions.
"""

import json
import os
import urllib.error
import urllib.request

import pytest

from tools.scrape_tool import scrape_tool
from tools.seo_audit_tool import seo_audit_tool
from tools.web_search_tool import get_last_web_search_diag, web_search_tool


@pytest.mark.live
def test_web_search_live_duckduckgo():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to hit real DuckDuckGo (needs internet).")

    results = web_search_tool("Next Level Tech Company Tunisia web development", max_results=5)
    assert isinstance(results, list), "Expected list"
    assert len(results) >= 1, (
        "DuckDuckGo/ddgs returned no results — check internet, firewall, VPN. "
        "Install/upgrade: pip install -U ddgs. "
        f"Diag: {get_last_web_search_diag()}"
    )
    first = results[0]
    assert first.get("url"), f"Missing url in row: {first}"
    assert str(first["url"]).startswith("http")


@pytest.mark.live
def test_lm_studio_chat_completion():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 for real LM Studio calls.")

    model = os.getenv("LM_VERIFY_MODEL", "").strip()
    if not model:
        pytest.skip("Set LM_VERIFY_MODEL to an exact LM Studio model id (e.g. phi-2). Load it in LM Studio first.")

    base = os.getenv("LM_STUDIO_BASE", "http://127.0.0.1:1234").rstrip("/")
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": 'Reply with exactly one word in English: OK'}],
        "temperature": 0.2,
        "max_tokens": 32,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        pytest.fail(f"LM Studio HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
    except urllib.error.URLError as e:
        pytest.fail(f"Cannot reach LM Studio at {base} — start Local Server. ({e})")

    choices = body.get("choices") or []
    assert choices, f"No choices in response: {body}"
    content = (choices[0].get("message") or {}).get("content") or ""
    assert str(content).strip(), f"Empty completion — is model `{model}` loaded in LM Studio? Raw: {body}"


@pytest.mark.live
def test_seo_audit_live_example_com():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 for real HTTP SEO audit (needs internet).")

    out = seo_audit_tool("https://example.com/")
    assert isinstance(out.get("seo_score"), int), out
    assert out["seo_score"] >= 0
    assert out.get("load_time_s") is not None
    assert out.get("url")


@pytest.mark.live
def test_scrape_live_example_com():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 for Playwright scrape (needs internet + playwright install chromium).")

    out = scrape_tool("https://example.com/")
    assert "error" not in out, out
    assert out.get("title")
    assert out.get("url") == "https://example.com/"


@pytest.mark.live
def test_minimal_pipeline_live_lm_studio(monkeypatch):
    """Discovery → Head using loaded LM Studio models + real DuckDuckGo."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 for full minimal pipeline (LM Studio + internet).")

    model = os.getenv("LM_VERIFY_MODEL", "").strip()
    if not model:
        pytest.skip("Set LM_VERIFY_MODEL to an exact LM Studio model id loaded in LM Studio.")

    monkeypatch.setenv("AGENT_MODEL_DISCOVERY", model)
    monkeypatch.setenv("AGENT_MODEL_HEAD", model)

    from agents.lm_client import reset_client_cache
    from config.settings import get_settings
    from workflows.main_pipeline import run_minimal_marketing_pipeline

    get_settings.cache_clear()
    reset_client_cache()
    try:
        out = run_minimal_marketing_pipeline("Next Level Tech Tunisia software", max_search_results=3)
    finally:
        get_settings.cache_clear()
        reset_client_cache()

    assert len(out["discovery"]["search_results"]) >= 1
    assert out["discovery"]["report_markdown"].strip()
    assert out["head_report_markdown"].strip()
