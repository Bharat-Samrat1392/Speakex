"""Keep credentials out of anything a user can see (UI, logs, downloads)."""

from __future__ import annotations

import os
import re

SECRET_ENV_VARS = ("GROQ_API_KEY", "HUGGINGFACE_TOKEN", "HF_TOKEN", "OPENAI_API_KEY")

# Common credential shapes: Groq keys, Hugging Face tokens, OpenAI-style keys, auth headers.
_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{6,}"),
    re.compile(r"hf_[A-Za-z0-9]{6,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"),
    re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"),
    re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+"),
]

MAX_DETAIL_CHARS = 300


def redact(text: object) -> str:
    """Return ``text`` with any known secret values or credential-looking strings masked."""
    message = str(text)
    for name in SECRET_ENV_VARS:
        value = os.getenv(name, "").strip().strip("'\"")
        if len(value) >= 6:
            message = message.replace(value, "[REDACTED]")
            # Partial echoes such as "gsk_abc***********xyz" still reveal a prefix/suffix.
            message = message.replace(value[:8], "[REDACTED]").replace(value[-6:], "[REDACTED]")
    for pattern in _PATTERNS:
        message = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", message)
    return message


def safe_detail(exc: BaseException) -> str:
    """A short, redacted description of an exception for user-facing messages."""
    detail = redact(f"{type(exc).__name__}: {exc}").strip()
    if len(detail) > MAX_DETAIL_CHARS:
        detail = detail[:MAX_DETAIL_CHARS].rstrip() + "…"
    return detail
