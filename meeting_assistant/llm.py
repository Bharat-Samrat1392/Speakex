"""Separate LLM stages via Groq: transcript-only refinement (#1) and structured analysis (#2)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import openai
from pydantic import ValidationError

from meeting_assistant.schemas import Analysis
from meeting_assistant.security import safe_detail

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# All provider configuration lives here. Groq exposes an OpenAI-compatible API, so the
# `openai` Python package is used only as an HTTP client pointed at Groq.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
REFINE_CHUNK_CHARS = 6000  # keeps each refinement call well inside Groq output/rate limits
UNSPECIFIED = "Unspecified"
_LABEL_RE = re.compile(r"^(SPEAKER_[A-Za-z0-9]+):", re.MULTILINE)


class LLMError(RuntimeError):
    """Raised when an LLM stage cannot be completed. Messages are safe to show users."""


def refinement_model() -> str:
    return os.getenv("REFINEMENT_MODEL", DEFAULT_MODEL)


def analysis_model() -> str:
    return os.getenv("ANALYSIS_MODEL", DEFAULT_MODEL)


def _client():
    from dotenv import load_dotenv

    load_dotenv(override=True)
    key = os.getenv("GROQ_API_KEY", "").strip().strip("'\"")
    if not key or key == "your_groq_api_key_here":
        raise LLMError("GROQ_API_KEY is missing. Add it to your .env file to run the two language-model stages.")
    try:
        base_url = os.getenv("GROQ_BASE_URL", "").strip().strip("'\"") or GROQ_BASE_URL
        # Retries honour Groq's retry-after header on 429s (free-tier token-per-minute limits).
        return openai.OpenAI(api_key=key, base_url=base_url, max_retries=5, timeout=180)
    except Exception as exc:
        raise LLMError(f"Could not initialize the Groq client. Details: {safe_detail(exc)}") from exc


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _complete(client, *, model: str, stage: str, effort: str | None = None, **kwargs):
    """Call Groq and translate every provider error into a credential-free LLMError."""
    if effort and model.startswith("openai/gpt-oss"):
        kwargs["extra_body"] = {"reasoning_effort": effort}
    try:
        return client.chat.completions.create(model=model, temperature=0, **kwargs)
    except openai.AuthenticationError:
        raise LLMError("Groq authentication failed. Please check GROQ_API_KEY.") from None
    except openai.PermissionDeniedError:
        raise LLMError(f"Groq refused access to model '{model}'. Check GROQ_API_KEY and the model name.") from None
    except openai.NotFoundError:
        raise LLMError(f"Groq model '{model}' was not found. Check REFINEMENT_MODEL / ANALYSIS_MODEL.") from None
    except openai.RateLimitError:
        raise LLMError(f"{stage}: Groq rate limit reached. Wait a minute and try again.") from None
    except openai.APIConnectionError:
        raise LLMError(f"{stage}: could not reach Groq. Check the internet connection.") from None
    except openai.APIStatusError as exc:
        if exc.status_code == 413:
            raise LLMError(f"{stage}: the transcript is too large for the current Groq plan's limits.") from None
        raise LLMError(f"{stage} failed (Groq HTTP {exc.status_code}). Details: {safe_detail(exc)}") from None
    except Exception as exc:
        raise LLMError(f"{stage} failed. Details: {safe_detail(exc)}") from None


def _strip_fence(text: str, lang: str = r"[a-zA-Z0-9_-]+") -> str:
    fenced = re.fullmatch(rf"```(?:{lang})?\s*(.*?)\s*```", text.strip(), flags=re.IGNORECASE | re.DOTALL)
    return fenced.group(1).strip() if fenced else text.strip()


# ---------------------------------------------------------------- LLM #1: refinement


def _split_long_block(block: str, limit: int) -> list[str]:
    """Split one oversized speaker turn at sentence boundaries, repeating its label."""
    match = _LABEL_RE.match(block)
    label = match.group(0) + " " if match else ""
    body = block[len(match.group(0)) :].strip() if match else block
    sentences = re.split(r"(?<=[.!?])\s+", body)
    parts, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > limit:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return [label + p for p in parts]


def chunk_transcript(text: str, limit: int = REFINE_CHUNK_CHARS) -> list[str]:
    """Group whole speaker turns into chunks of at most ~limit characters."""
    blocks: list[str] = []
    for block in (b.strip() for b in text.split("\n\n")):
        if block:
            blocks.extend(_split_long_block(block, limit) if len(block) > limit else [block])
    chunks, current = [], []
    size = 0
    for block in blocks:
        if current and size + len(block) > limit:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _refinement_problem(raw: str, refined: str) -> str | None:
    """Return why a refined chunk can't be trusted, or None if it passes the checks."""
    if not refined:
        return "empty output"
    if _LABEL_RE.findall(raw) != _LABEL_RE.findall(refined):
        return "speaker labels were changed"
    if len(raw) > 300 and not (0.6 <= len(refined) / len(raw) <= 1.6):
        return "length changed too much (possible summarizing or truncation)"
    return None


def refine_transcript_checked(raw_transcript: str) -> tuple[str, list[str]]:
    """LLM #1: correct recognition errors/terminology only. Returns (refined text, warnings).

    Every chunk is checked: speaker labels must be identical and in the same order, and the
    text must not shrink/grow drastically. A chunk that fails keeps its raw text.
    """
    client = _client()
    system = _prompt("refine_transcript.txt")
    refined_chunks, warnings = [], []
    chunks = chunk_transcript(raw_transcript)
    for index, chunk in enumerate(chunks, start=1):
        response = _complete(
            client,
            model=refinement_model(),
            stage="Transcript refinement",
            effort="low",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"RAW TRANSCRIPT (untrusted text to edit):\n{chunk}"},
            ],
        )
        choice = response.choices[0]
        refined = _strip_fence(choice.message.content or "")
        problem = "output was cut off" if getattr(choice, "finish_reason", None) == "length" else None
        problem = problem or _refinement_problem(chunk, refined)
        if problem:
            warnings.append(f"Refinement of transcript part {index}/{len(chunks)} was rejected ({problem}); raw text kept for that part.")
            refined_chunks.append(chunk)
        else:
            refined_chunks.append(refined)
    return "\n\n".join(refined_chunks), warnings


def refine_transcript(raw_transcript: str) -> str:
    return refine_transcript_checked(raw_transcript)[0]


# ---------------------------------------------------------------- LLM #2: analysis


def _extract_json(content: str) -> Any:
    """Parse a JSON object, tolerating common code-fence wrappers."""
    cleaned = _strip_fence(content, "json")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # Recover a single object if the model added a short preamble or suffix.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError("Response did not contain valid JSON.") from exc


_PLACEHOLDERS = {"", "unspecified", "none", "n/a", "na", "null", "unknown", "not specified", "tbd", "unassigned", "not mentioned"}
_STOPWORDS = {"the", "and", "for", "end", "next", "of", "by", "on", "at", "in", "to", "a", "an", "speaker"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _grounded(value: str, transcript_words: set[str]) -> bool:
    """True if a meaningful word of `value` actually occurs in the transcript."""
    tokens = [t for t in _words(value) if len(t) >= 3 and t not in _STOPWORDS] or [
        t for t in _words(value) if t not in {"speaker"}
    ]
    return any(t in transcript_words for t in tokens)


def _apply_action_item_defaults(payload: dict[str, Any], transcript: str | None = None) -> dict[str, Any]:
    """Normalise missing owners/deadlines to 'Unspecified' and drop ones not found in the transcript."""
    transcript_words = _words(transcript) if transcript is not None else None
    items = payload.get("action_items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in ("owner", "deadline"):
                value = item.get(field)
                if not isinstance(value, str) or value.strip().lower().strip(".") in _PLACEHOLDERS:
                    item[field] = UNSPECIFIED
                elif transcript_words is not None and not _grounded(value, transcript_words):
                    item[field] = UNSPECIFIED  # never keep an owner/deadline the transcript doesn't mention
    return payload


def analyze_transcript(refined_transcript: str) -> Analysis:
    """LLM #2 analyzes only the refined transcript; output is schema-validated (one retry if malformed)."""
    client = _client()
    messages = [
        {"role": "system", "content": _prompt("analyze_meeting.txt")},
        {"role": "user", "content": f"REFINED TRANSCRIPT (the only source of facts):\n{refined_transcript}"},
    ]
    last_problem = ""
    for _attempt in range(2):
        try:
            response = _complete(
                client,
                model=analysis_model(),
                stage="Meeting analysis",
                effort="medium",
                response_format={"type": "json_object"},
                messages=messages,
            )
        except LLMError as exc:
            # Groq rejects json_object replies that aren't valid JSON with HTTP 400; retry once.
            if "HTTP 400" in str(exc) and "json" in str(exc).lower():
                last_problem = "the model produced invalid JSON"
                continue
            raise
        try:
            parsed = _extract_json(response.choices[0].message.content or "")
            if not isinstance(parsed, dict):
                raise ValueError("Response must be a JSON object.")
            return Analysis.model_validate(_apply_action_item_defaults(parsed, refined_transcript))
        except (ValidationError, ValueError) as exc:
            last_problem = safe_detail(exc)
    raise LLMError(f"Meeting analysis returned malformed or invalid structured data: {last_problem}")
