"""Focused tests for hallucination guards, refinement checks, chunking and secret redaction."""

import json

import openai
import pytest

import meeting_assistant.llm as llm
from meeting_assistant.security import redact
from meeting_assistant.transcription import TranscriptionError, load_audio


def _fake_client(*contents):
    """A stand-in Groq client returning the given message contents in order."""
    replies = list(contents)

    class Completions:
        @staticmethod
        def create(**_kwargs):
            content = replies.pop(0)
            choice = type("Choice", (), {"message": type("M", (), {"content": content})(), "finish_reason": "stop"})()
            return type("Resp", (), {"choices": [choice]})()

    return type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()


def test_invented_owner_and_deadline_become_unspecified(monkeypatch):
    transcript = "SPEAKER_00: Maybe someone could prepare the report.\n\nSPEAKER_01: I will update the dashboard by Friday."
    reply = {
        "summary": "Reports were discussed.",
        "minutes": [],
        "decisions": [],
        "action_items": [
            {"task": "Prepare the report", "owner": "Rahul", "deadline": "October 30"},
            {"task": "Update the dashboard", "owner": "SPEAKER_01", "deadline": "by Friday"},
        ],
    }
    monkeypatch.setattr(llm, "_client", lambda: _fake_client(json.dumps(reply)))
    items = llm.analyze_transcript(transcript).action_items
    assert (items[0].owner, items[0].deadline) == ("Unspecified", "Unspecified")
    assert (items[1].owner, items[1].deadline) == ("SPEAKER_01", "by Friday")


def test_malformed_analysis_is_retried_once(monkeypatch):
    good = '{"summary":"ok","minutes":[],"decisions":[],"action_items":[]}'
    monkeypatch.setattr(llm, "_client", lambda: _fake_client("not json", good))
    assert llm.analyze_transcript("SPEAKER_00: ok").summary == "ok"


def test_refinement_that_renames_speakers_is_rejected(monkeypatch):
    raw = "SPEAKER_00: we deploy on cubernetes.\n\nSPEAKER_01: i will check the yaml."
    renamed = "Rahul: We deploy on Kubernetes.\n\nSPEAKER_01: I will check the YAML."
    monkeypatch.setattr(llm, "_client", lambda: _fake_client(renamed))
    refined, warnings = llm.refine_transcript_checked(raw)
    assert refined == raw
    assert warnings and "speaker labels" in warnings[0]


def test_refinement_accepts_label_preserving_corrections(monkeypatch):
    raw = "SPEAKER_00: we deploy on cubernetes.\n\nSPEAKER_01: i will check the yaml."
    fixed = "SPEAKER_00: We deploy on Kubernetes.\n\nSPEAKER_01: I will check the YAML."
    monkeypatch.setattr(llm, "_client", lambda: _fake_client(fixed))
    assert llm.refine_transcript_checked(raw) == (fixed, [])


def test_chunking_keeps_every_turn_and_label():
    turns = [f"SPEAKER_0{i % 3}: " + ("word " * 400).strip() + "." for i in range(12)]
    text = "\n\n".join(turns)
    chunks = llm.chunk_transcript(text, limit=3000)
    assert len(chunks) > 1
    assert "\n\n".join(chunks) == text


def test_auth_error_never_echoes_the_key(monkeypatch):
    secret = "gsk_" + "A1b2C3d4E5f6G7h8I9j0" * 2
    monkeypatch.setenv("GROQ_API_KEY", secret)

    class Completions:
        @staticmethod
        def create(**_kwargs):
            import httpx

            request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            response = httpx.Response(401, request=request)
            raise openai.AuthenticationError(f"Invalid API Key {secret[:10]}...{secret[-4:]}", response=response, body=None)

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    monkeypatch.setattr(llm, "_client", lambda: client)
    with pytest.raises(llm.LLMError) as info:
        llm.analyze_transcript("SPEAKER_00: hi")
    assert str(info.value) == "Groq authentication failed. Please check GROQ_API_KEY."
    assert secret[:10] not in str(info.value)


def test_redact_masks_env_secrets_and_token_shapes(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_SuperSecretValue123456")
    text = redact("failed with hf_SuperSecretValue123456 and Authorization: Bearer abc.def and gsk_zzzzzzzzzzzz")
    assert "SuperSecret" not in text and "abc.def" not in text and "gsk_zzz" not in text


def test_empty_and_corrupt_files_raise_clear_errors(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(TranscriptionError, match="empty"):
        load_audio(empty)
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"this is not audio" * 100)
    with pytest.raises(TranscriptionError, match="Could not decode"):
        load_audio(corrupt)
