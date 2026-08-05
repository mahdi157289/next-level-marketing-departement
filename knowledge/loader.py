"""Load company knowledge base for agent prompts."""

from __future__ import annotations

from pathlib import Path

_KB: str | None = None


def _load_kb() -> str:
    global _KB
    if _KB is not None:
        return _KB
    path = Path(__file__).resolve().parent / "company_profile.md"
    if not path.exists():
        _KB = ""
        return _KB
    _KB = path.read_text(encoding="utf-8")
    return _KB


def company_context(max_chars: int = 1200) -> str:
    kb = _load_kb()
    if not kb:
        return ""
    # Extract overview + service categories + ICP
    sections = []
    capture = False
    for line in kb.split("\n"):
        if line.startswith("## "):
            capture = line.strip("## ").strip() in (
                "Company Overview",
                "Service Categories",
                "Target Client Profiles",
            )
        if capture:
            sections.append(line)
    text = "\n".join(sections).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…"
    return text


def qualification_criteria() -> str:
    kb = _load_kb()
    if not kb:
        return ""
    lines = []
    capture = False
    for line in kb.split("\n"):
        if line.startswith("## Lead Qualification Criteria"):
            capture = True
        elif line.startswith("## ") and capture:
            break
        if capture:
            lines.append(line)
    return "\n".join(lines).strip()


def service_summary() -> str:
    kb = _load_kb()
    if not kb:
        return ""
    lines = []
    capture = False
    for line in kb.split("\n"):
        if line.startswith("## Service Categories"):
            capture = True
        elif line.startswith("## ") and capture:
            break
        if capture:
            lines.append(line)
    return "\n".join(lines).strip()
