"""Lead Completion Agent — inspect leads for missing fields and fill gaps with tools.

Runs after discovery ingestion (auto) or on demand (backfill). For each lead it
computes which FILLABLE_FIELDS are empty, then picks tools based on the existing
fields:
  * no google_maps_url   -> google_maps_search by name (+country), best match
  * missing maps fields  -> google_maps_place re-scrape of the maps URL
  * missing email/phone/socials/description -> website scrape (scrape tool)
  * missing business_type -> tiny LLM classification (best-effort)
  * missing seo_score    -> seo_audit
  * missing country      -> deterministic inference from address/URL

Rule: only currently-empty fields are ever written (enrich_missing), so
re-scrapes can never regress existing data.
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, List, Optional

from agents import lm_client
from agents.discovery_agent import DiscoveryAgent
from crm import service
from crm.client import AgentRunRecorder
from tools.registry import resolve_callable

# Fields a re-scraped Maps hit can supply.
_MAPS_HIT_FIELDS = (
    "google_maps_url", "address", "rating", "review_count", "phone", "email",
    "industry", "hours", "description", "price_level", "facebook", "instagram",
    "linkedin", "twitter", "tags",
)

_SOCIAL_KEYS = ("facebook", "instagram", "linkedin", "twitter")

_LLM_CLASSIFY_CATEGORIES = (
    "retail, wholesale, services, agency, software, ecommerce, restaurant, "
    "real estate, education, logistics, manufacturing, healthcare, government, "
    "ngo, hospitality, finance, construction, media, other"
)


# --- name matching (maps lookup by name) ---


def _norm_tokens(s: str) -> List[str]:
    s = (s or "").lower()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c) and (c.isalnum() or c == " ")
    )
    return re.sub(r"\s+", " ", s).strip().split()


def name_similarity(a: str, b: str) -> float:
    """Token Jaccard-style overlap (0..1). 'AS AGENCY - Agence Web Tunis' vs
    'AS AGENCY Agence Web Tunis' scores high; unrelated names score low."""
    ta, tb = _norm_tokens(a), _norm_tokens(b)
    if not ta or not tb:
        return 0.0
    a_set, b_set = set(ta), set(tb)
    overlap = sum(1 for x in ta if x in b_set)
    union = len(a_set | b_set)
    return overlap / union if union else 0.0


# --- tool helpers ---


def _website_url(url: str) -> Optional[str]:
    return DiscoveryAgent._website_url(url)


def _hit_to_lead_data(lead: Dict[str, Any], hit: Dict[str, Any]) -> Dict[str, Any]:
    """Map a normalized maps hit to lead data — only fields currently empty."""
    gaps = set(service.lead_gaps(lead))
    mapping: Dict[str, Any] = {
        "google_maps_url": hit.get("google_maps_url"),
        "address": hit.get("address"),
        "rating": hit.get("rating"),
        "review_count": hit.get("review_count"),
        "phone": hit.get("phone"),
        "email": hit.get("email"),
        "industry": hit.get("category"),
        "hours": hit.get("hours"),
        "description": hit.get("description"),
        "price_level": hit.get("price_level"),
        "facebook": hit.get("facebook"),
        "instagram": hit.get("instagram"),
        "linkedin": hit.get("linkedin"),
        "twitter": hit.get("twitter"),
        "tags": hit.get("tags"),
    }
    if "country" in gaps:
        mapping["country"] = service._infer_country(hit)
    return {
        k: v for k, v in mapping.items()
        if k in gaps and v not in (None, "", [], {})
    }


def _lookup_maps_best(lead: Dict[str, Any], min_similarity: float = 0.5) -> Optional[Dict[str, Any]]:
    """Search Maps by name (+country), return the best name match above threshold."""
    name = (lead.get("name") or "").strip()
    if len(name) < 2:
        return None
    country = (lead.get("country") or "").strip()
    query = f"{name} {country}".strip() if country else f"{name} Tunisia"
    gm_fn = resolve_callable("google_maps_search")
    if not gm_fn:
        return None
    try:
        hits = gm_fn(query, region="Tunisia", max_results=5)
    except BaseException:
        return None
    best: Optional[Dict[str, Any]] = None
    best_score = min_similarity
    for h in hits:
        score = name_similarity(name, h.get("title") or "")
        if score > best_score:
            best_score = score
            best = h
    return best


def _scrape_site(site: str) -> Optional[Dict[str, Any]]:
    scrape_fn = resolve_callable("scrape")
    if not scrape_fn:
        return None
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            out = pool.submit(scrape_fn, site).result(timeout=20)
    except BaseException:
        return None
    if not isinstance(out, dict) or out.get("error"):
        return None
    data: Dict[str, Any] = {}
    emails = out.get("emails") or []
    phones = out.get("phones") or []
    if emails:
        data["email"] = emails[0]
    if phones:
        data["phone"] = phones[0]
    for k in _SOCIAL_KEYS:
        v = (out.get("socials") or {}).get(k)
        if v:
            data[k] = v
    desc = (out.get("description") or "").strip()
    if desc:
        data["description"] = desc
    return data or None


def _classify_business_type(lead: Dict[str, Any]) -> Optional[str]:
    title = (lead.get("name") or "").strip()
    if not title:
        return None
    site = _website_url(lead.get("url") or "")
    prompt = (
        "Classify this company's business type with a short label (2-5 words, lowercase).\n"
        f"Categories: {_LLM_CLASSIFY_CATEGORIES}.\n"
        f"Company: {title}\nWebsite: {site or 'unknown'}\nLabel:"
    )
    try:
        agent = DiscoveryAgent()
        text = lm_client.chat_completion(
            agent.model,
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=16,
        )
    except BaseException:
        return None
    label = (text or "").strip().splitlines()[0].strip()[:64]
    return label or None


def _seo_audit(site: str) -> Optional[int]:
    seo_fn = resolve_callable("seo_audit")
    if not seo_fn:
        return None
    try:
        out = seo_fn(site)
        score = out.get("seo_score") if isinstance(out, dict) else None
        return int(score) if score is not None else None
    except BaseException:
        return None


# --- per-lead enrichment ---


def _enrich_one(
    lead: Dict[str, Any],
    run: Any,
    should_cancel: Callable[[], bool],
) -> Dict[str, Any]:
    lid = str(lead["id"])
    if should_cancel():
        return {"lead_id": lid, "cancelled": True, "filled": [], "steps": []}
    before = set(service.lead_gaps(lead))
    steps: List[str] = []

    # 1) Maps data — re-scrape existing maps URL, else look up by name.
    maps_fields = before & set(_MAPS_HIT_FIELDS)
    if maps_fields:
        gm_url = (lead.get("google_maps_url") or "").strip()
        if "google.com/maps" in gm_url:
            run.record_api("playwright", "google_maps_place")
            place_fn = resolve_callable("google_maps_place")
            maps_hit = place_fn(gm_url) if place_fn else None
            if maps_hit:
                steps.append("maps_place")
        else:
            run.record_api("playwright", "google_maps_search")
            maps_hit = _lookup_maps_best(lead)
            if maps_hit:
                steps.append("maps_lookup")
        if maps_hit:
            data = _hit_to_lead_data(lead, maps_hit)
            if data:
                service.enrich_missing(lid, data, agent_run_id=run.id)

    # 2) Website scrape — email / phone / socials / description.
    site = _website_url(lead.get("url") or "")
    if site and (before & {"email", "phone", "facebook", "instagram", "linkedin", "twitter", "description"}):
        run.record_api("scrape", "page")
        scrape_data = _scrape_site(site)
        if scrape_data:
            service.enrich_missing(lid, scrape_data, agent_run_id=run.id)
            steps.append("website")

    # 3) business_type via tiny LLM call (best-effort, skips on rate limit).
    if "business_type" in before:
        run.record_api("litellm", "chat")
        label = _classify_business_type(lead)
        if label:
            service.enrich_missing(lid, {"business_type": label}, agent_run_id=run.id)
            steps.append("llm")

    # 4) seo_score audit.
    if "seo_score" in before and site:
        run.record_api("seo_audit", "audit")
        score = _seo_audit(site)
        if score is not None:
            service.enrich_missing(lid, {"seo_score": score}, agent_run_id=run.id)
            steps.append("seo")

    refreshed = service.get_lead(lid) or lead
    after = set(service.lead_gaps(refreshed))
    filled = sorted(before - after)
    return {"lead_id": lid, "cancelled": False, "filled": filled, "steps": steps}


# --- batch entry point ---


def enrich_leads(
    lead_ids: List[str],
    *,
    recorder: AgentRunRecorder,
    should_cancel: Optional[Callable[[], bool]] = None,
    max_workers: int = 1,
) -> Dict[str, Any]:
    """Inspect + complete a batch of leads. Records an 'enrich' agent_run."""
    should_cancel = should_cancel or (lambda: False)
    if not recorder.pipeline_run_id:
        recorder.start_pipeline()

    leads = [service.get_lead(str(lid)) for lid in lead_ids]
    leads = [l for l in leads if l is not None]

    results: List[Dict[str, Any]] = []
    filled_counts: Dict[str, int] = {}
    step_counts: Dict[str, int] = {}
    errors: List[Dict[str, Any]] = []

    with recorder.agent_run("enrich", model="n/a", input_summary=f"enrich {len(leads)} leads") as run:
        for lead in leads:
            if should_cancel():
                break
            try:
                res = _enrich_one(lead, run, should_cancel)
            except Exception as exc:  # noqa: BLE001
                errors.append({"lead_id": str(lead["id"]), "error": str(exc)[:200]})
                continue
            results.append(res)
            if not res.get("cancelled"):
                run.increment_records(1)
            for f in res.get("filled", []):
                filled_counts[f] = filled_counts.get(f, 0) + 1
            for s in res.get("steps", []):
                step_counts[s] = step_counts.get(s, 0) + 1

        run.set_output(
            summary=f"enriched {len(results)} leads, filled {sum(filled_counts.values())} fields",
            json={
                "processed": len(results),
                "filled_by_field": filled_counts,
                "steps": step_counts,
                "errors": errors,
            },
        )

    return {
        "pipeline_run_id": recorder.pipeline_run_id,
        "status": "success",
        "processed": len(results),
        "filled_by_field": filled_counts,
        "steps": step_counts,
        "errors": errors,
        "results": results,
    }
