# Hunt Tools Catalog + Start Hunting Implementation Plan

## Goal

Make `web_search`, `site_extract`, and `research` usable by every agent; rename the CRM
button to "Start hunting"; hunt **empty plus unrealistic** lead fields via web search +
site extraction with a safe overwrite path; and highlight every field a hunt run changed
in cyan in the UI.

## Architecture

A deterministic value-validator (`crm/value_validation.py`) feeds three consumers —
`research()` (hunts suspicious + empty fields), a new `service.enrich_hunt()` write path
(fills empties, overwrites only suspicious values with validated ones), and the enrich
workflow (which records `hunted_fields` inside the existing `leads.research` JSON, so the
UI needs no schema migration). Tool availability is broadened in the catalog, roster, and
scout tool-schemas; migration `0016` enables the tools on all existing profiles.

## Tech Stack

Python/FastAPI/SQLAlchemy/Alembic, pytest, Vitest/React Query (Vite), Crawl4AI, SearXNG/DDGS.

## Global Constraints

- Keep catalog id `web_search` (no rename to `search`, no second tool).
- Keep `research` in the catalog, exposed to all agents (do NOT remove it).
- `enrich_missing` keeps gap-only semantics; overwriting a populated field happens **only**
  in `enrich_hunt`, and **only** when the current value is unrealistic and the new value validates.
- `hunted_fields` lives inside the existing `leads.research` JSON column — no schema migration.
- Highlight color is `--cyan` (`#22d3ee`). Label: "Start hunting" / "Hunting…".
- Do not touch `migrations/versions/20260810_0013_hunter_research.py`/`20260811_0014_research_tool.py`
  or rename `tests/test_hunter_db.py`.
- Backend: `python -m pytest -q`; DB tests gated on `DATABASE_URL`. Frontend: `cd web && npm test`.
- Frequent small commits.

---

## Task 1: Value validator

**Files:** Create `crm/value_validation.py`, `tests/test_value_validation.py`.

Produces `is_unrealistic_value(field, value) -> bool` (never `True` for unknown fields).
Rules: placeholders (`n/a, na, -, none, null, unknown, tbd, x, to be determined`) flag any
string field; `rating` 0–5; `review_count` 0–1_000_000; `seo_score` 0–100; `email` strict
regex + reject `@example.*`/`test.com`; `phone` 7–15 digits; `hours` >= 3 chars + digit or
day word; `country` alpha-only 2–64; `industry`/`business_type` 2–128 chars; `address`
>= 5 chars + a space; `description` >= 8 chars; `price_level` <= 16 chars; `tags` non-empty;
socials plausible (URL on a known host, or `@handle`).

## Task 2: Tools everywhere

- `tools/registry.py`: `web_search` + `site_extract` `agents` -> all 7 roster names.
- `crm/agents_registry.py`: 6 non-discovery agents `default_tools` ->
  `["llm_chat", "research", "web_search", "site_extract"]`.
- `crm/scout.py`: add `site_extract` + `research` function schemas to `_TOOLS_SCHEMA`.
- Tests updated in `tests/test_research_tool.py`, `tests/test_agent_roster.py`.

## Task 3: Migration `20260811_0016_agent_tools_everywhere.py`

Append `web_search` + `site_extract` (dedup) to every `agent_profiles.enabled_tools`;
downgrade removes them. `down_revision = "20260811_0015"`.

## Task 4: `research()` hunts suspicious fields

`tools/research_tool.py`: default gaps = `_is_empty(v) or is_unrealistic_value(c, v)`.

## Task 5: `service.lead_problems` + `enrich_hunt`

- `lead_problems(lead) -> {field: "unrealistic"}` over `FILLABLE_FIELDS`.
- `enrich_hunt(lead_id, data)`: fill empty; overwrite only when `is_unrealistic(cur) and
  not is_unrealistic(new)`; else skip. Delegates to `enrich_lead`.

## Task 6: Workflow hunts + records `hunted_fields`

`workflows/enrich_leads.py`: capture `probs_before`; run research when no research OR
problems exist; write research results via `enrich_hunt`; after refresh compute
`hunted = sorted((gaps_before - gaps_after) | (probs_before - probs_after))` and merge
`res["hunted_fields"] = hunted` into the stored research dict (replace) via `enrich_lead`.

## Task 7: Frontend

- `web/src/api/types.ts`: `hunted_fields?: string[] | null` on `research`.
- `web/src/pages/Leads.tsx`: button "Start hunting"/"Hunting…", subtitle + messages; per-lead
  cyan-highlight matching `<td>`s; 🎯 marker.
- `web/src/pages/LeadsDetail.tsx`: rows as `[label, value, fieldKey]` triples; cyan cells;
  legend.
- `web/src/styles/components.css`: `.hunted`, `.hunted-dot`.
- Tests in `Leads.test.tsx`, `LeadsDetail.test.tsx`.

## Task 8: Docs + full verification

- This plan doc; `python -m pytest -q`; `alembic upgrade head` + `downgrade -1`; `npm test`.
- Commit per task.