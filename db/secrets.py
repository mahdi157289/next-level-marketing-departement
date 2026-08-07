"""Encrypted-at-rest storage for agent/provider secrets.

Secrets are stored in the ``agent_secrets`` table (per-agent, keyed by provider)
as Fernet tokens. A single ``SECRET_ENCRYPTION_KEY`` (base64 Fernet key) is read
from the environment / ``.env``; if absent a clear-text warning is logged and
encryption is skipped (tokens fall back to plaintext) so the app still runs in
local dev without a configured key.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore


def _get_fernet():
    key = os.getenv("SECRET_ENCRYPTION_KEY")
    if not key or Fernet is None:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


_fernet = _get_fernet()
if not _fernet:
    logger.warning(
        "SECRET_ENCRYPTION_KEY not set (or cryptography unavailable); "
        "agent secrets will be stored as plaintext tokens. Set a base64 Fernet "
        "key before production use."
    )


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    token = _fernet.encrypt(plaintext.encode("utf-8")) if _fernet else plaintext.encode("utf-8")
    return token.decode("utf-8")


def decrypt_secret(token: str) -> Optional[str]:
    if not token:
        return None
    if not _fernet:
        return token
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None
