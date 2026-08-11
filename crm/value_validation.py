"""Deterministic 'unrealistic value' rules for lead fields (hunting target set).

The enrich workflow and ``research()`` hunt fields that are either empty OR look
broken/unrealistic (placeholders, impossible ranges, malformed emails/phones).
Unknown fields are never flagged, so hunting behavior for non-FILLABLE columns
is unchanged.
"""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDERS = {"n/a", "na", "-", "none", "null", "unknown", "tbd", "x", "to be determined"}

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,24}$")
_DAY_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)\b", re.IGNORECASE)
_ALPHA_RE = re.compile(r"^[A-Za-zÀ-ÿ ]+$")
_SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "linkedin.com",
    "twitter.com", "x.com", "t.co", "linkedin.com/company",
)
_EMAIL_FAKE_DOMAINS = {"example.com", "example.org", "example.net", "test.com"}


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDERS


_KNOWN_FIELDS = frozenset({
    "rating", "review_count", "seo_score", "email", "phone", "hours",
    "country", "industry", "business_type", "address", "description",
    "price_level", "tags", "facebook", "instagram", "linkedin", "twitter",
})


def is_unrealistic_value(field: str, value: Any) -> bool:
    """True when ``value`` for a known lead field looks broken/junk.

    Unknown fields always return False. Empty values are NOT unrealistic
    (empty is handled separately by ``_is_empty`` / ``lead_gaps``).
    """
    if field not in _KNOWN_FIELDS:
        return False
    if value is None or value == "":
        return False
    if _is_placeholder(value):
        return True
    if field == "rating":
        return not isinstance(value, (int, float)) or not (0 <= float(value) <= 5)
    if field == "review_count":
        return not isinstance(value, (int, float)) or not (0 <= float(value) <= 1_000_000)
    if field == "seo_score":
        return not isinstance(value, (int, float)) or not (0 <= float(value) <= 100)
    if field == "email":
        s = str(value).strip()
        if " " in s or not _EMAIL_RE.match(s):
            return True
        return s.rsplit("@", 1)[-1].lower() in _EMAIL_FAKE_DOMAINS
    if field == "phone":
        digits = re.sub(r"\D", "", str(value))
        return not (7 <= len(digits) <= 15)
    if field == "hours":
        s = str(value).strip()
        if len(s) < 3:
            return True
        return not (re.search(r"\d", s) or _DAY_RE.search(s))
    if field == "country":
        s = str(value).strip()
        return not (2 <= len(s) <= 64 and _ALPHA_RE.match(s))
    if field in ("industry", "business_type"):
        s = str(value).strip()
        return not (2 <= len(s) <= 128)
    if field == "address":
        s = str(value).strip()
        return len(s) < 5 or " " not in s
    if field == "description":
        s = str(value).strip()
        return len(s) < 8
    if field == "price_level":
        s = str(value).strip()
        return len(s) > 16
    if field == "tags":
        return isinstance(value, (list, dict)) and not value
    if field in ("facebook", "instagram", "linkedin", "twitter"):
        s = str(value).strip().lower()
        if not s or s in {"facebook", "instagram", "linkedin", "twitter"}:
            return True
        if s.startswith(("http", "www.")):
            return not any(host in s for host in _SOCIAL_HOSTS)
        return not (s.startswith("@") and 1 <= len(s) <= 128)
    return False