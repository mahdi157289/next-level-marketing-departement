"""Skill health checks (green/red/amber lamps) — injected fake registry, no network."""

from __future__ import annotations

import time

from crm import skill_health


def test_run_skill_checks_with_fake_registry():
    def fake_ok():
        time.sleep(0.05)
        return {"status": "ok", "detail": "fine"}

    def fake_slow():
        time.sleep(2.0)
        return {"status": "ok", "detail": "too slow"}

    def fake_skip():
        return {"status": "skip", "detail": "no key"}

    def fake_raise():
        raise RuntimeError("boom")

    checkers = {
        "web_search": fake_ok,
        "llm_chat": fake_slow,
        "seo_audit": fake_skip,
        "scrape": fake_raise,
    }
    budgets = {"web_search": 5.0, "llm_chat": 0.2, "seo_audit": 5.0, "scrape": 5.0}

    out = skill_health.run_skill_checks(checkers=checkers, budgets=budgets)
    by_id = {r["skill_id"]: r for r in out}

    assert by_id["web_search"]["status"] == "ok"
    assert by_id["web_search"]["latency_ms"] >= 0
    assert by_id["llm_chat"]["status"] == "fail"
    assert "timed out" in by_id["llm_chat"]["detail"]
    assert by_id["seo_audit"]["status"] == "skip"
    assert by_id["scrape"]["status"] == "fail"
    assert "RuntimeError" in by_id["scrape"]["detail"]
    # Catalog order preserved.
    assert [r["skill_id"] for r in out] == ["web_search", "llm_chat", "seo_audit", "scrape"]


def test_run_skill_checks_empty_and_unknown_keys():
    assert skill_health.run_skill_checks(checkers={}) == []
    # Registry covers every catalog skill that has a check + every check is catalog-known.
    for sid in skill_health.SKILL_CHECKS:
        assert sid in {t["id"] for t in skill_health.TOOL_CATALOG}


def test_verdict_helpers():
    assert skill_health._ok("x") == {"status": "ok", "detail": "x"}
    assert skill_health._fail("x") == {"status": "fail", "detail": "x"}
    assert skill_health._skip("x") == {"status": "skip", "detail": "x"}
