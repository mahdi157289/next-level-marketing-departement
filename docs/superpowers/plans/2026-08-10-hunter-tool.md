# Hunter Tool — CRM Lead Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `hunter` catalog tool that detects empty lead columns, runs field-targeted web searches to find the missing values, fills them via the gap-only CRM path, and stores an investigation summary + evidence sources in a new `leads.research` JSON column.

**Architecture:** `tools/hunter_tool.py` is a self-contained, never-raising tool that (1) discovers huntable columns from the live `leads` schema, (2) builds ≤8 queries (2 context + one per missing field, generic fallback for unknown columns), (3) runs `web_search_tool`, (4) mines values with the existing scrape validators, (5) LLM-synthesizes a summary with a deterministic fallback. Registered in `tools/registry.py`, added to every agent profile's `enabled_tools`, invoked by the enrich workflow (`_enrich_one`) and by any agent via scout `_execute_tool`.

**Tech Stack:** Python 3.9, SQLAlchemy 2.x, Alembic, FastAPI, DuckDuckGo search (`ddgs`), LLM via `agents.lm_client`, React/TypeScript/Vitest.

## Global Constraints

- `DATABASE_URL` for DB tests: `postgresql://admin:secret@127.0.0.1:5433/marketing_db` (real local PG, alembic revision must be ≤ `20260809_0011` before applying 0013).
- Tool must NEVER raise — all tool/search/LLM calls wrapped, status field returned.
- Only gap-only writes via `service.enrich_missing` — never overwrite populated fields.
- Huntable columns = `Lead.__table__.columns` minus denylist `{id, created_at, updated_at, status, status_notes, source, url, google_maps_url}`.
- Max queries per lead: `MAX_QUERIES = 8`.
- Backend tests: `python -m pytest tests/test_hunter_tool.py -q` (set `DATABASE_URL`). Frontend: `npm test` in `web/`.
- Spec: `docs/superpowers/specs/2026-08-10-hunter-tool-design.md`.

---

### Task 1: Migration + model — `leads.research` column & profile enabled_tools

**Files:**
- Create: `migrations/versions/20260810_0013_hunter_research.py`
- Modify: `db/models.py` (add `research` column to `Lead`)

**Interfaces:**
- Produces: `leads.research` JSON column (nullable); every `agent_profiles.enabled_tools` includes `"hunter"`; `Lead.research` attribute.

- [ ] **Step 1: Write the failing test** (new `tests/test_hunter_db.py`)

```python
"""DB tests for the hunter research column."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from crm import service
from db.models import Lead


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(Lead).where(Lead.url == url))
        conn.commit()
    eng.dispose()


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_lead_research_roundtrip():
    url = f"https://hunt-db-{uuid.uuid4().hex[:8]}.tn"
    lead = service.create_lead({"name": "Hunt DB Co", "url": url, "source": "pytest"})
    try:
        out = service.enrich_missing(
            str(lead["id"]),
            {"research": {"summary": "x", "fields_found": {"email": "a@b.tn"}, "status": "ok"}},
        )
        assert out["research"]["summary"] == "x"
        assert out["research"]["fields_found"]["email"] == "a@b.tn"
    finally:
        _cleanup(url)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hunter_db.py::test_lead_research_roundtrip -q`
Expected: FAIL — `UndefinedColumn: column leads.research does not exist`

- [ ] **Step 3: Write migration**

```python
"""Add leads.research + enable hunter tool on all profiles.

Revision ID: 20260810_0013
Revises: 20260809_0011
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0013"
down_revision: Union[str, None] = "20260809_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("research", sa.JSON(), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT agent_name, enabled_tools FROM agent_profiles WHERE enabled_tools IS NOT NULL"
    )).fetchall()
    for agent_name, enabled_tools in rows:
        tools = list(enabled_tools or [])
        if "hunter" not in tools:
            tools.append("hunter")
        conn.execute(
            sa.text("UPDATE agent_profiles SET enabled_tools = :t WHERE agent_name = :n"),
            {"t": tools, "n": agent_name},
        )


def downgrade() -> None:
    op.drop_column("leads", "research")
```

- [ ] **Step 4: Add model column** — in `db/models.py` after `tags = Column(JSON)` (line ~54):

```python
    research = Column(JSON)
```

- [ ] **Step 5: Persist `research` in `crm/service.py`** — `enrich_lead` (line ~297) has a hardcoded whitelist; without adding `research` here, `enrich_missing` silently drops it (the loop never sets the attribute), and the roundtrip test stays red.

Add `"research"` to the whitelist tuple:

```python
        for key in (
            "email", "phone", "industry", "country", "business_type", "seo_score",
            "address", "google_maps_url", "rating", "review_count",
            "hours", "description", "price_level", "facebook", "instagram",
            "linkedin", "twitter", "tags", "research",
        ):
```

And special-case the dict value *before* `_clean_field` (which would stringify it), mirroring the `tags` branch:

```python
            elif key == "research":
                val = val if isinstance(val, dict) else None
            elif key == "tags":
                val = val if isinstance(val, list) else None
```

- [ ] **Step 6: Apply migration + run test**

Run:
```
$env:DATABASE_URL="postgresql://admin:secret@127.0.0.1:5433/marketing_db"; python -m alembic upgrade head
```
Then: `python -m pytest tests/test_hunter_db.py::test_lead_research_roundtrip -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/20260810_0013_hunter_research.py db/models.py crm/service.py tests/test_hunter_db.py
git commit -m "feat: add leads.research column + persist research via enrich"
```

---

### Task 2: Hunter core — dynamic columns, gap detection, query builder

**Files:**
- Create: `tools/hunter_tool.py`
- Test: `tests/test_hunter_tool.py`

**Interfaces:**
- Produces:
  - `_huntable_columns() -> List[str]`
  - `_domain(url: str) -> str`
  - `_build_queries(name, url, industry, country, gaps) -> List[str]`

- [ ] **Step 1: Write the failing tests**

```python
from tools.hunter_tool import _build_queries, _domain, _huntable_columns


def test_huntable_columns_exclude_denylist():
    cols = _huntable_columns()
    assert "email" in cols
    assert "research" not in cols
    assert "id" not in cols
    assert "status" not in cols
    assert "url" not in cols


def test_build_queries_has_context_and_per_gap():
    qs = _build_queries("Acme", url="https://www.acme.tn", industry="agency", country="Tunisia", gaps=["email", "phone"])
    assert qs[0] == "Acme Tunisia"
    assert "site:acme.tn" in qs
    assert any("email" in q for q in qs)
    assert any("phone" in q or "telephone" in q or "tel" in q for q in qs)
    assert len(qs) <= 8


def test_build_queries_generic_fallback_for_unknown_column():
    qs = _build_queries("Acme", country="Tunisia", gaps=["vat_number"])
    assert any("vat number" in q for q in qs)


def test_domain_strips_www_and_scheme():
    assert _domain("https://www.acme.tn/") == "acme.tn"
    assert _domain("http://acme.com") == "acme.com"
    assert _domain("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hunter_tool.py -q`
Expected: FAIL — module/import errors

- [ ] **Step 3: Implement hunter core**

```python
"""hunter — CRM-driven lead investigation tool.

Detects empty columns on a lead from the live `leads` schema, runs
field-targeted web searches to hunt for the missing values, mines them with
the same validators as the scrape tool, and returns a knowledge summary +
evidence sources. Never raises; reports status instead.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from db.models import Lead

MAX_QUERIES = 8

HUNT_DENYLIST = {
    "id", "created_at", "updated_at", "status", "status_notes",
    "source", "url", "google_maps_url", "research",
}

# field -> query template. "{name}" = lead name; "{domain}" = lead domain.
_FIELD_QUERY_TEMPLATES = {
    "email": "{name} email OR contact",
    "phone": "{name} phone OR telephone OR tel",
    "facebook": "{name} facebook",
    "instagram": "{name} instagram",
    "linkedin": "{name} linkedin",
    "twitter": "{name} twitter OR x.com",
    "address": "{name} address OR adresse",
    "industry": "{name} services OR \"what they do\"",
    "business_type": "{name} services OR \"what they do\"",
    "hours": "{name} hours OR horaires OR opening",
    "description": "{name} about OR \"qui sommes-nous\"",
    "price_level": "{name} reviews OR category",
    "tags": "{name} reviews OR category",
    "country": "{name} city OR country",
    "rating": "{name} reviews",
    "review_count": "{name} reviews",
    "seo_score": "site:{domain}",
}


def _huntable_columns() -> List[str]:
    """All leads-table columns minus the denylist (schema-driven, future-proof)."""
    return [c.name for c in Lead.__table__.columns if c.name not in HUNT_DENYLIST]


def _column_human(field: str) -> str:
    return field.replace("_", " ")


def _domain(url: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _query_for_field(field: str, name: str, domain: str = "") -> str:
    tpl = _FIELD_QUERY_TEMPLATES.get(field)
    if not tpl:
        return f"{name} {_column_human(field)}"
    if "{domain}" in tpl:
        return tpl.format(domain=domain) if domain else f"{name} {_column_human(field)}"
    return tpl.format(name=name)


def _build_queries(
    name: str,
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
) -> List[str]:
    name = (name or "").strip()
    if not name:
        return []
    domain = _domain(url)
    queries: List[str] = []
    queries.append(f"{name} {country}".strip() if country else name)
    if domain:
        queries.append(f"site:{domain}")
    for field in gaps or []:
        q = _query_for_field(field, name, domain)
        if q not in queries:
            queries.append(q)
    return queries[:MAX_QUERIES]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hunter_tool.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/hunter_tool.py tests/test_hunter_tool.py
git commit -m "feat: hunter core - schema-driven columns + gap-targeted query builder"
```

---

### Task 3: Field mining + summary + `hunter()` orchestration

**Files:**
- Modify: `tools/hunter_tool.py`
- Test: `tests/test_hunter_tool.py`

**Interfaces:**
- Consumes: `tools.web_search_tool._relevance_score`, `tools.scrape_tool._clean_phone`, `tools.scrape_tool._extract_socials`, `agents.lm_client.chat_completion`, `tools.registry.resolve_callable("web_search")`.
- Produces: `_mine_field(field, hits) -> Any`, `_synthesize_summary(name, industry, country, hits) -> str`, `hunter(name="", url="", industry="", country="", gaps=None, **fields) -> Dict`.

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import patch

from tools.hunter_tool import _mine_field, hunter

HITS = [
    {"title": "Acme - Contact", "url": "https://acme.tn/contact",
     "snippet": "Email hello@acme.tn or call +216 71 123 456. Facebook: facebook.com/acme.tn Instagram: instagram.com/acme"},
    {"title": "Acme", "url": "https://acme.tn", "snippet": "Acme is a web agency in Tunis"},
]


def test_mine_email_and_phone():
    assert _mine_field("email", HITS) == "hello@acme.tn"
    assert "+216" in _mine_field("phone", HITS)


def test_mine_socials_from_snippets():
    socials = _mine_field("facebook", HITS)
    assert socials == "https://facebook.com/acme.tn"


def test_mine_unknown_field_uses_best_snippet():
    val = _mine_field("vat_number", HITS)
    assert isinstance(val, str) and len(val) > 0


def test_hunter_returns_full_payload_and_fills_gaps():
    with patch("tools.hunter_tool._run_searches", return_value=HITS), \
         patch("tools.hunter_tool._synthesize_summary", return_value="Acme is an agency."):
        out = hunter(name="Acme", url="https://acme.tn", country="Tunisia", gaps=["email", "phone"])
    assert out["status"] == "ok"
    assert out["summary"] == "Acme is an agency."
    assert out["fields_found"]["email"] == "hello@acme.tn"
    assert out["queries"]
    assert out["sources"]


def test_hunter_never_raises_on_search_failure():
    with patch("tools.hunter_tool._run_searches", return_value=[]), \
         patch("tools.hunter_tool._synthesize_summary", return_value=""):
        out = hunter(name="Acme")
    assert out["status"] == "no_results"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hunter_tool.py -q`
Expected: FAIL — `_mine_field`/`hunter` not defined

- [ ] **Step 3: Implement mining + summary + orchestration** (append to `tools/hunter_tool.py`)

```python
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _hit_blob(hits):
    return " ".join(
        f"{h.get('title', '')} {h.get('snippet', '')} {h.get('url', '')}"
        for h in hits
    )


def _mine_field(field: str, hits: List[Dict[str, Any]]) -> Any:
    if field == "email":
        m = _EMAIL_RE.search(_hit_blob(hits))
        return m.group(0) if m else None
    if field == "phone":
        for h in hits:
            blob = f"{h.get('title', '')} {h.get('snippet', '')}"
            for cand in re.findall(r"\+?[\d\s\-().]{7,15}", blob):
                from tools.scrape_tool import _clean_phone

                cleaned = _clean_phone(cand)
                if cleaned:
                    return cleaned
        return None
    if field in ("facebook", "instagram", "linkedin", "twitter"):
        from tools.scrape_tool import _extract_socials

        return _extract_socials(_hit_blob(hits)).get(field)
    if field in ("hours",):
        for h in hits:
            blob = f"{h.get('title', '')} {h.get('snippet', '')}"
            for cand in re.findall(
                r"\b(?:mon|tue|wed|thu|fri|sat|sun|lu|ma|me|je|ve|sa|di)"
                r"[a-z]*\.?\s*[-–]\s*[a-z]*\.?|\b24\s*h\b|\b\d{1,2}[:h]\d{0,2}\s*[-–]\s*\d{1,2}[:h]\d{0,2}\b",
                blob,
                re.IGNORECASE,
            ):
                return cand
        return None
    if field == "description":
        return (hits[0].get("snippet") or "")[:500] if hits else None
    if field in ("industry", "business_type"):
        for h in hits[:3]:
            snip = (h.get("snippet") or "").strip()
            if snip:
                return snip[:128]
        return None
    # Generic: best snippet mentioning the humanized column name.
    kw = field.replace("_", " ")
    best = None
    for h in hits:
        snip = (h.get("snippet") or "").strip()
        if snip and (kw in snip.lower() or kw.split()[-1] in snip.lower()):
            return snip[:256]
        best = best or snip[:256]
    return best


def _synthesize_summary(name: str, industry: str, country: str, hits: List[Dict[str, Any]]) -> str:
    from agents.lm_client import chat_completion
    from config.settings import get_settings

    snippets = "\n".join(
        f"- {h.get('title', '')}: {h.get('snippet', '')}" for h in hits[:12]
    )
    prompt = (
        "Write a short markdown intelligence profile of a company from web search results.\n"
        "Sections: ## Overview, ## Services, ## Online presence, ## What we found.\n"
        f"Company: {name}\nIndustry: {industry or 'unknown'}\nCountry: {country or 'unknown'}\n"
        f"Search results:\n{snippets}\nProfile:"
    )
    try:
        text = chat_completion(
            get_settings().agent_model_discovery,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
        text = (text or "").strip()
        if text:
            return text
    except BaseException:
        pass
    # Deterministic fallback.
    lines = [f"## Overview\n{name} ({country or 'unknown'})."]
    top = (hits[0].get("snippet") or "").strip() if hits else ""
    if top:
        lines.append(f"**Key finding:** {top[:400]}")
    lines.append(f"## Sources\n" + "\n".join(f"- {h.get('title', '')}: {h.get('url', '')}" for h in hits[:5]))
    return "\n".join(lines)


def _run_searches(queries: List[str], max_per_query: int = 5) -> List[Dict[str, Any]]:
    from tools.registry import resolve_callable
    from tools.web_search_tool import _relevance_score, web_search_tool

    fn = resolve_callable("web_search") or web_search_tool
    seen: set = set()
    collected: List[Dict[str, Any]] = []
    for q in queries:
        try:
            for h in fn(q, max_results=max_per_query) or []:
                url = (h.get("url") or "").rstrip("/")
                if url and url not in seen:
                    seen.add(url)
                    collected.append(h)
        except BaseException:
            continue
    return sorted(collected, key=lambda h: _relevance_score(h, queries[0] if queries else ""), reverse=True)[:15]


def hunter(
    name: str = "",
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Investigate a lead: detect empty columns, web-search them, mine values, summarize."""
    pseudo = {"name": name, "url": url, "industry": industry, "country": country, **fields}
    if gaps is None:
        gaps = [c for c in _huntable_columns() if c not in HUNT_DENYLIST and not _is_empty(pseudo.get(c))]
    queries = _build_queries(name, url=url, industry=industry, country=country, gaps=gaps)
    if not queries:
        return {"summary": "", "fields_found": {}, "sources": [], "queries": [], "status": "no_results",
                "investigated_at": _now()}
    hits = _run_searches(queries)
    if not hits:
        return {"summary": "", "fields_found": {}, "sources": [], "queries": queries, "status": "no_results",
                "investigated_at": _now()}
    fields_found = {}
    for field in gaps:
        try:
            val = _mine_field(field, hits)
        except BaseException:
            val = None
        if val not in (None, "", [], {}):
            fields_found[field] = val
    summary = _synthesize_summary(name, industry, country, hits)
    status = "llm_fallback" if not summary or summary.startswith("## Overview\n" + name) else "ok"
    if not summary:
        summary = f"## Overview\n{name}"
        status = "llm_fallback"
    sources = [
        {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": (h.get("snippet") or "")[:300], "query": queries[0]}
        for h in hits[:10]
    ]
    return {
        "summary": summary,
        "fields_found": fields_found,
        "sources": sources,
        "queries": queries,
        "status": status,
        "investigated_at": _now(),
    }


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if value == 0:
        return True
    return False


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hunter_tool.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/hunter_tool.py tests/test_hunter_tool.py
git commit -m "feat: hunter field mining + summary + orchestration"
```

---

### Task 4: Registry + agent roster — hunter available to every agent

**Files:**
- Modify: `tools/registry.py` (`TOOL_CATALOG`, `resolve_callable`)
- Modify: `crm/agents_registry.py` (`default_tools`)
- Test: `tests/test_hunter_tool.py`

**Interfaces:**
- Produces: `resolve_callable("hunter")` returns callable; `validate_tool_ids(["hunter"], agent_name=any)` passes; every roster agent's `default_tools` includes `"hunter"`.

- [ ] **Step 1: Write the failing tests**

```python
from tools.registry import TOOL_CATALOG, resolve_callable, validate_tool_ids
from crm.agents_registry import AGENT_ROSTER


def test_hunter_in_catalog_for_all_agents():
    entry = next(t for t in TOOL_CATALOG if t["id"] == "hunter")
    assert set(entry["agents"]) == {a["name"] for a in AGENT_ROSTER}


def test_hunter_resolves():
    assert callable(resolve_callable("hunter"))


def test_hunter_valid_for_every_agent():
    for a in AGENT_ROSTER:
        validate_tool_ids(["hunter"], agent_name=a["name"])


def test_hunter_in_all_roster_default_tools():
    for a in AGENT_ROSTER:
        assert "hunter" in a["default_tools"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hunter_tool.py -k "catalog or resolves or valid or roster" -q`
Expected: FAIL

- [ ] **Step 3: Implement registry + roster**

In `tools/registry.py`, add to `TOOL_CATALOG` (after the `scrape` entry, line ~52):

```python
    {
        "id": "hunter",
        "label": "CRM lead investigation: hunt missing fields via web search",
        "agents": [
            "discovery", "head", "qualifier", "categorization",
            "analysis", "outreach", "content",
        ],
    },
```

In `resolve_callable` (after the `scrape` branch):

```python
    if tool_id == "hunter":
        from tools.hunter_tool import hunter

        return hunter
```

In `crm/agents_registry.py`, add `"hunter"` to every agent's `default_tools` list (discovery line ~16, and the single-tool entries for head/qualifier/categorization/analysis/outreach/content → `["llm_chat", "hunter"]`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hunter_tool.py -k "catalog or resolves or valid or roster" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/registry.py crm/agents_registry.py tests/test_hunter_tool.py
git commit -m "feat: register hunter in catalog for all agents"
```

---

### Task 5: Enrich workflow — hunt step

**Files:**
- Modify: `workflows/enrich_leads.py` (`_enrich_one`)
- Test: `tests/test_enrich_leads.py`

**Interfaces:**
- Consumes: `hunter` callable via `resolve_callable("hunter")`, `service.enrich_missing`.
- Produces: `_enrich_one` writes `research` + `fields_found` when `research` gap exists; adds `"hunt"` to steps.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_enrich_one_hunts_missing_fields():
    from unittest.mock import patch
    from workflows.enrich_leads import _enrich_one
    from crm.client import _AgentRunContext

    url = _unique_url("huntstep")
    lead = service.create_lead({
        "name": "HuntStep Co", "url": url, "source": "pytest",
        "google_maps_url": "https://google.com/maps/place/x",
        "address": "Tunis", "rating": 4.5, "review_count": 10,
        "country": "Tunisia", "industry": "Software", "business_type": "software",
        "email": "a@huntstep.tn", "phone": "+21611111111", "seo_score": 80,
        "hours": "Mon-Fri", "description": "d", "price_level": "$$",
        "facebook": "https://fb.co/h", "instagram": "https://ig.co/h",
        "linkedin": "https://ln.co/h", "twitter": "https://x.co/h", "tags": ["x"],
    })
    try:
        fake = {
            "summary": "HuntStep summary",
            "fields_found": {"email": "ops@huntstep.tn", "facebook": "https://facebook.com/huntstep"},
            "sources": [{"title": "t", "url": "https://s.tn", "snippet": "s"}],
            "queries": ["q"], "status": "ok",
        }
        run = _AgentRunContext(str(lead["id"]))
        with patch("workflows.enrich_leads.resolve_callable", return_value=lambda *a, **k: fake):
            res = _enrich_one(lead, run, lambda: False)
        assert "hunt" in res["steps"]
        fresh = service.get_lead(str(lead["id"]))
        assert fresh["research"]["summary"] == "HuntStep summary"
        assert fresh["research"]["fields_found"]["email"] == "ops@huntstep.tn"
        assert fresh["email"] == "a@huntstep.tn"  # gap-only: pre-filled field untouched
    finally:
        _cleanup(url)
```

Note: the lead is created with **every** `FILLABLE_FIELDS` populated so steps 1-4 (maps/scrape/llm/seo) are skipped and only the hunt step runs — keeps the test hermetic (no real LLM/tool calls). `research` is not in `lead_gaps()`, so the hunt step must check the raw field, not `before`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_enrich_leads.py::test_enrich_one_hunts_missing_fields -q`
Expected: FAIL — `research` not filled / `hunt` not in steps

- [ ] **Step 3: Implement the hunt step** in `_enrich_one` (after the seo step, before `refreshed`):

```python
    # 5) Web-search investigation for any remaining gaps (research summary).
    if not lead.get("research"):
        hunter_fn = resolve_callable("hunter")
        if hunter_fn:
            run.record_api("ddgs", "hunter")
            try:
                hunt = hunter_fn(
                    name=lead.get("name") or "",
                    url=lead.get("url") or "",
                    industry=lead.get("industry") or "",
                    country=lead.get("country") or "",
                )
            except BaseException:
                hunt = None
            if hunt and (hunt.get("fields_found") or hunt.get("summary")):
                data = {"research": hunt}
                if hunt.get("fields_found"):
                    data.update(hunt["fields_found"])
                service.enrich_missing(lid, data, agent_run_id=run.id)
                steps.append("hunt")
```

`lead_gaps()` only returns `FILLABLE_FIELDS` (`crm/service.py` line ~50), so `research` never appears in `before` — the condition must be `not lead.get("research")` (None/{} is falsy) rather than `"research" in before`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_enrich_leads.py::test_enrich_one_hunts_missing_fields -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add workflows/enrich_leads.py tests/test_enrich_leads.py
git commit -m "feat: enrich workflow runs hunter to fill gaps + research summary"
```

---

### Task 6: API schema — expose `research`

**Files:**
- Modify: `crm/schemas.py` (`LeadOut`)
- Test: `tests/test_api_router.py`

**Interfaces:**
- Produces: `/api/leads/{id}` detail includes `research`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_api_lead_detail_returns_research(client):
    url = f"https://api-research-{uuid.uuid4().hex[:8]}.example.com"
    r = client.post("/api/leads", json={"name": "Research Co", "url": url, "source": "pytest"})
    lead_id = r.json()["id"]
    eng = create_engine(_database_url())
    with eng.begin() as conn:
        conn.execute(text("UPDATE leads SET research = :r WHERE id = :id"),
                     {"r": json.dumps({"summary": "s", "status": "ok"}), "id": uuid.UUID(lead_id)})
    eng.dispose()
    try:
        r = client.get(f"/api/leads/{lead_id}")
        assert r.status_code == 200, r.text
        assert r.json()["research"]["summary"] == "s"
    finally:
        eng = create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM lead_events WHERE lead_id = :id"), {"id": uuid.UUID(lead_id)})
            conn.execute(text("DELETE FROM leads WHERE id = :id"), {"id": uuid.UUID(lead_id)})
        eng.dispose()
```

Add `import json` to the imports at the top of `tests/test_api_router.py`:

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_router.py::test_api_lead_detail_returns_research -q`
Expected: FAIL — Pydantic response excludes `research`

- [ ] **Step 3: Add to `LeadOut`** (after `tags`, line 85):

```python
    research: Optional[dict] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_router.py::test_api_lead_detail_returns_research -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add crm/schemas.py tests/test_api_router.py
git commit -m "feat: expose leads.research in API schemas"
```

---

### Task 7: Frontend — types + Research panel + indicator

**Files:**
- Modify: `web/src/api/types.ts` (`Lead`)
- Modify: `web/src/pages/LeadsDetail.tsx`
- Modify: `web/src/pages/Leads.tsx`
- Test: `web/src/pages/LeadsDetail.test.tsx` (create), `web/src/pages/Leads.test.tsx`

**Interfaces:**
- Consumes: `Lead.research?: { summary?: string; sources?: Array<{title?: string; url?: string; snippet?: string}>; status?: string } | null`
- Produces: Research panel in `LeadsDetail`; research indicator in leads table.

- [ ] **Step 1: Write the failing tests**

`web/src/pages/LeadsDetail.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import LeadsDetail from "./LeadsDetail";
import * as leadsApi from "../api/leads";

function renderDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(leadsApi, "fetchLead").mockResolvedValue({
    id: "l1", name: "Acme", url: "https://acme.tn", status: "enriched", source: "discovery",
    lead_score: 42, updated_at: null, created_at: null, google_maps_url: null, address: "Tunis",
    rating: 4.5, review_count: 12, country: "Tunisia", industry: "Logistics", business_type: "SaaS",
    email: "hi@acme.tn", phone: "+21622", seo_score: 61, status_notes: null, hours: null,
    description: null, price_level: null, facebook: null, instagram: null, linkedin: null,
    twitter: null, tags: null,
    research: { summary: "Acme is a logistics SaaS in Tunis.", status: "ok",
      sources: [{ title: "Acme site", url: "https://acme.tn", snippet: "s" }] },
    events: [],
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/leads/l1"]}>
        <Routes>
          <Route path="/leads/:id" element={<LeadsDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LeadsDetail", () => {
  it("renders the research summary and sources", async () => {
    renderDetail();
    expect(await screen.findByText(/Research/i)).toBeInTheDocument();
    expect(screen.getByText(/Acme is a logistics SaaS/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Acme site" });
    expect(link).toHaveAttribute("href", "https://acme.tn");
  });
});
```

`web/src/pages/Leads.test.tsx` — extend the existing render test's mock lead with `research: null` (the type now requires it) and add:
```tsx
it("shows a research indicator on enriched leads", async () => {
  vi.spyOn(leadsApi, "fetchLeads").mockResolvedValue([
    { ...existingMockLead, research: { summary: "s", status: "ok", sources: [] } },
  ]);
  renderLeads();
  expect(await screen.findByText("Acme")).toBeInTheDocument();
  expect(screen.getByTitle(/research/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run src/pages/LeadsDetail.test.tsx src/pages/Leads.test.tsx`
Expected: FAIL — type errors / no Research panel

- [ ] **Step 3: Add the type** in `web/src/api/types.ts` inside `interface Lead`:

```ts
  research: {
    summary?: string | null;
    status?: string | null;
    queries?: string[] | null;
    fields_found?: Record<string, unknown> | null;
    sources?: Array<{ title?: string | null; url?: string | null; snippet?: string | null }> | null;
  } | null;
```

- [ ] **Step 4: Render the panel** in `web/src/pages/LeadsDetail.tsx` — after the maps link paragraph and before the info panel, add:

```tsx
      {lead.research ? (
        <div className="panel">
          <h3>Research</h3>
          {lead.research.status === "ok" ? null : (
            <p className="muted">Status: {lead.research.status}</p>
          )}
          {lead.research.summary ? (
            <div style={{ whiteSpace: "pre-wrap", marginBottom: 12 }}>{lead.research.summary}</div>
          ) : (
            <p className="muted">No summary.</p>
          )}
          {lead.research.sources?.length ? (
            <>
              <h4>Sources</h4>
              <ul>
                {lead.research.sources.map((s, i) => (
                  <li key={i}>
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}</a>
                    ) : (
                      s.title
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
```

- [ ] **Step 5: Add the indicator** in `web/src/pages/Leads.tsx` — in the table cell where status badge renders (or next to the lead name), add:

```tsx
                {lead.research ? (
                  <span title="Research available" style={{ cursor: "default" }}>🔎</span>
                ) : null}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npx vitest run src/pages/LeadsDetail.test.tsx src/pages/Leads.test.tsx`
Expected: PASS

- [ ] **Step 7: Typecheck**

Run: `npx tsc --noEmit`
Expected: no output (clean)

- [ ] **Step 8: Commit**

```bash
git add web/src/api/types.ts web/src/pages/LeadsDetail.tsx web/src/pages/Leads.tsx web/src/pages/LeadsDetail.test.tsx web/src/pages/Leads.test.tsx
git commit -m "feat: show lead research summary + sources in UI"
```

---

### Task 8: Full verification

**Files:**
- Test: whole suite

- [ ] **Step 1: Run backend suite**

Run: `$env:DATABASE_URL="postgresql://admin:secret@127.0.0.1:5433/marketing_db"; python -m pytest -q -p no:cacheprovider`
Expected: all pass (existing 152 + new tests)

- [ ] **Step 2: Run frontend suite + build**

Run (in `web/`): `npm test` then `npm run build`
Expected: all pass; build succeeds

- [ ] **Step 3: Live smoke test (optional)** — run `hunter` on one real lead:

Run: `python -c "from tools.hunter_tool import hunter; import json; print(json.dumps(hunter(name='WEBI', url='https://www.webi.tn/', country='Tunisia', gaps=['email','instagram']), ensure_ascii=True)[:800])"`
Expected: a payload with `status`, `fields_found`, `sources`, `summary`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify hunter end to end"
```

---

## Notes

- Migration `UPDATE` on `enabled_tools` must run only after confirming column type is JSON/JSONB — verify with `\d agent_profiles` if the aggregate form errors; the per-row fallback is provided.
- The `hunter` signature accepts `**fields` so an agent calling `hunter(name="Acme", url="...", industry="agency", country="Tunisia")` works through `_execute_tool`'s `fn(**args)`.
- Reuse `_clean_phone`, `_extract_socials`, `_relevance_score` — do not reimplement.
