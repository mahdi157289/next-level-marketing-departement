# Hunter Tool — CRM-Driven Lead Investigation (Design)

Date: 2026-08-10
Status: Approved for implementation

## Problem

The CRM holds 100+ discovered leads with many empty columns. Existing tools
find new leads (`web_search`, `meta_ads_search`, `google_maps_search`) or fill
a narrow slice from one source (`scrape` = one website, `google_maps_place` =
Maps, `seo_audit` = SEO). Nothing looks at the CRM state and hunts for the
specific values still missing. The operator wants a single tool that:

1. Detects which lead columns are empty (including columns added in the
   future — schema-driven, no hardcoded field list).
2. Runs deep, field-specific web searches targeted at each missing value.
3. Mines the results and fills the missing columns.
4. Stores an investigation summary (digest + evidence sources) as an extra
   info column on the lead.

## Design

### Tool: `tools/hunter_tool.py` (catalog id `hunter`)

```python
def hunter(
    name: str = "",
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
    **fields: Any,
) -> Dict[str, Any]:
```

Returns (never raises):

```json
{
  "summary": "<markdown digest>",
  "fields_found": {"email": "...", "phone": "...", "facebook": "..."},
  "sources": [{"title": "...", "url": "...", "snippet": "...", "query": "..."}],
  "queries": ["...", "..."],
  "status": "ok | llm_fallback | no_results",
  "investigated_at": "2026-08-10T..."
}
```

Behavior:

- **Dynamic column discovery** — `_huntable_columns()` reads the live
  `leads` schema from `Lead.__table__.columns` and subtracts a denylist:
  `id`, `created_at`, `updated_at`, `status`, `status_notes`, `source`, `url`.
  Any column present on the model and empty on the lead is hunted. New
  columns added to the model later are hunted automatically.
- **Gap detection** — `gaps` param wins if provided (enrich workflow passes
  the exact computed gaps); otherwise computed from the empty huntable
  columns on the assembled pseudo-lead.
- **Query building** — always two context queries (`"{name} {country}"`,
  `site:{domain}` when a real URL exists) plus one targeted query per gap.
  Targeted query = field-specific template map with a generic fallback
  `"{name} {column name humanized}"` for unknown columns. Cap total at
  `MAX_QUERIES = 8`.
- **Field mining** — for each gap, extract a value from the aggregated hits
  using validators from `tools/scrape_tool` (email regex, `_clean_phone`,
  social URLs) plus a generic best-snippet fallback for unknown fields.
- **Summary** — one LLM call synthesizes the digest (overview · services ·
  presence · what we found); deterministic fallback digest when LLM is
  unavailable (`status: "llm_fallback"`).

### Catalog + any-agent access

- `tools/registry.py`: `TOOL_CATALOG` entry
  `{"id": "hunter", "label": "CRM lead investigation: hunt missing fields via web search", "agents": [all roster agents]}`
  and `resolve_callable("hunter")`.
- `crm/agents_registry.py`: add `"hunter"` to every agent's `default_tools`.
- Migration DML appends `hunter` to `enabled_tools` of all existing
  `agent_profiles` rows (profiles are authoritative).

### Storage

New column `leads.research` (JSON, nullable):

```json
{
  "summary": "...",
  "fields_found": {...},
  "sources": [...],
  "queries": [...],
  "status": "ok",
  "investigated_at": "..."
}
```

### Enrich workflow integration

`workflows/enrich_leads.py::_enrich_one` adds a hunt step: when `research`
is empty, call `hunter(...)`, then `service.enrich_missing` writes
`fields_found` into the missing columns and `research` into the new column.
Gap-only — never overwrites populated fields.

### API + UI

- `Lead`/`LeadDetail` include `research`.
- `LeadsDetail.tsx` renders a Research panel: summary + clickable sources.
- Leads table shows a subtle indicator when `research` is present.

### Tests

- Unit: dynamic column discovery, gap→query templates + generic fallback,
  field mining with validators, LLM-fallback summary, dedupe/rank.
- DB: `research` persists; gap-only respected.
- Scout wiring: `hunter` runs via `_execute_tool` when enabled.
- Frontend: detail page renders the panel.

### Migration

`20260810_0013_hunter_research.py` = DDL (`leads.research` JSON) + DML
(append `hunter` to all profiles' `enabled_tools`).
