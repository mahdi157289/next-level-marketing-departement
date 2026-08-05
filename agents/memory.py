"""Agent memory: learns from past qualification results to improve future scouting."""

from __future__ import annotations

from typing import Any, Dict, List

from db.session import SessionLocal
from sqlalchemy import text


def build_lesson_summary(max_leads: int = 30) -> str:
    """Query past CRM leads with scores and return a lessons-learned summary."""
    session = SessionLocal()
    try:
        rows = session.execute(
            text("""
                SELECT name, url, lead_score, status_notes, source
                FROM leads
                WHERE lead_score > 0
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": max_leads},
        ).all()
    finally:
        session.close()

    if not rows:
        return (
            "No qualified past leads yet. General guidance: prefer actual businesses "
            "(companies with websites, agencies, stores) over directories, news, or blogs. "
            "Look for companies that need web development, data dashboards, marketing, or automation."
        )

    scored = [(r[0] or "", r[1] or "", r[2] or 0, r[3] or "", r[4] or "") for r in rows]
    hot = [s for s in scored if s[2] >= 35]
    warm = [s for s in scored if 25 <= s[2] < 35]
    cold = [s for s in scored if s[2] < 25]

    lines = ["## Agent Memory: Lessons from Past Scouting\n"]
    if hot:
        lines.append(f"### What Worked (Hot leads, score >= 35, {len(hot)} found)")
        for name, url, score, notes, src in hot[:5]:
            lines.append(f"- **{name[:50]}** ({score}) — {notes[:100]}")
        if hot:
            patterns = _common_patterns(hot)
            if patterns:
                lines.append(f"  Pattern: {patterns}")

    if cold:
        lines.append(f"\n### What Didn't Work (Cold leads, score < 25, {len(cold)} found)")
        for name, url, score, notes, src in cold[:5]:
            lines.append(f"- {name[:50]} ({score}) — {notes[:80]}")
        patterns = _common_patterns(cold)
        if patterns:
            lines.append(f"  Pattern to avoid: {patterns}")

    total = len(scored)
    avg = sum(s[2] for s in scored) / total if total > 0 else 0
    lines.append(
        f"\n### Summary: {total} leads evaluated, avg score {avg:.0f}/50. "
        f"Hot: {len(hot)}, Warm: {len(warm)}, Cold: {len(cold)}. "
        "Prioritize real businesses with clear digital needs over directories, news, or blogs."
    )
    return "\n".join(lines)


def _common_patterns(leads: List) -> str:
    """Simple heuristic: detect common domain patterns."""
    domains: Dict[str, int] = {}
    for _, url, _, _, _ in leads:
        for d in ["youtube", "blog", "news", "wikipedia", "reddit", "medium"]:
            if d in url.lower():
                domains[d] = domains.get(d, 0) + 1
    if domains:
        common = sorted(domains.items(), key=lambda x: -x[1])[:3]
        return ", ".join(f"{d} ({c}x)" for d, c in common)
    return ""
