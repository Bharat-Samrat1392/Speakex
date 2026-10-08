import pytest

from meeting_assistant.exporters import record_as_markdown
from meeting_assistant import pipeline
from meeting_assistant.llm import LLMError, analyze_transcript
from meeting_assistant.schemas import ActionItem, Analysis, MeetingRecord


def test_missing_action_owner_and_deadline_are_rejected():
    with pytest.raises(Exception):
        ActionItem(task="Send draft", owner="", deadline="")


def test_markdown_includes_both_transcripts_and_analysis():
    record = MeetingRecord(
        source_filename="meeting.wav",
        raw_transcript="We may launch in May.",
        refined_transcript="We may launch in May.",
        analysis=Analysis(summary="Launch timing was discussed."),
    )
    output = record_as_markdown(record)
    assert "## Raw transcript" in output
    assert "## Refined transcript" in output
    assert "Launch timing was discussed." in output
    assert "## Key decisions" in output


def test_pipeline_keeps_transcript_and_uses_empty_analysis_on_llm_failure(monkeypatch):
    from meeting_assistant.transcription import TranscriptSegment
    from meeting_assistant.diarization import SpeakerTurn

    monkeypatch.setattr(pipeline, "load_audio", lambda _path: "decoded-audio")
    monkeypatch.setattr(pipeline, "transcribe_segments", lambda _path: [TranscriptSegment(start=0.0, end=2.0, text="We might ship next month.")])
    monkeypatch.setattr(pipeline, "diarize", lambda _path: [SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00")])
    monkeypatch.setattr(pipeline, "refine_transcript_checked", lambda text: (text, []))
    monkeypatch.setattr(pipeline, "analyze_transcript", lambda _text: (_ for _ in ()).throw(LLMError("bad JSON")))

    record = pipeline.MeetingPipeline().process("unused.wav", source_filename="meeting.wav")

    assert "SPEAKER_00: We might ship next month." in record.raw_transcript
    assert record.raw_transcript == record.refined_transcript
    assert record.analysis == Analysis()
    assert any("analysis unavailable" in warning.lower() for warning in record.warnings)


def test_pipeline_refinement_failure_falls_back_to_raw_and_labels_it(monkeypatch):
    from meeting_assistant.transcription import TranscriptSegment
    from meeting_assistant.diarization import SpeakerTurn

    monkeypatch.setattr(pipeline, "load_audio", lambda _path: "decoded-audio")
    monkeypatch.setattr(pipeline, "transcribe_segments", lambda _path: [TranscriptSegment(start=0.0, end=2.0, text="We might ship next month.")])
    monkeypatch.setattr(pipeline, "diarize", lambda _path: [SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00")])
    monkeypatch.setattr(pipeline, "refine_transcript_checked", lambda _text: (_ for _ in ()).throw(LLMError("offline")))
    monkeypatch.setattr(pipeline, "analyze_transcript", lambda _text: Analysis(summary="Timing was discussed."))

    record = pipeline.MeetingPipeline().process("unused.wav", source_filename="meeting.wav")

    assert record.raw_transcript == record.refined_transcript
    assert record.analysis.summary == "Timing was discussed."
    assert any("shown unchanged" in warning for warning in record.warnings)



def test_missing_action_owner_and_deadline_default_to_unspecified(monkeypatch):
    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            class Message:
                content = '{"summary":"Review was discussed.","minutes":[],"decisions":[],"action_items":[{"task":"Review the draft"}]}'

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("meeting_assistant.llm._client", lambda: FakeClient())
    result = analyze_transcript("Review the draft.")

    assert result.action_items[0].owner == "Unspecified"
    assert result.action_items[0].deadline == "Unspecified"


def test_malformed_analysis_json_is_reported_as_recoverable_llm_error(monkeypatch):
    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            class Message:
                content = "This is not JSON"

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("meeting_assistant.llm._client", lambda: FakeClient())
    with pytest.raises(LLMError, match="malformed or invalid structured data"):
        analyze_transcript("The transcript is the source.")


def test_action_items_none_and_na_normalize_to_unspecified(monkeypatch):
    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            class Message:
                content = '{"summary":"Discussed launch.","minutes":[],"decisions":[],"action_items":[{"task":"Prepare slides","owner":"none","deadline":"N/A"}]}'

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("meeting_assistant.llm._client", lambda: FakeClient())
    result = analyze_transcript("Prepare slides.")

    assert result.action_items[0].owner == "Unspecified"
    assert result.action_items[0].deadline == "Unspecified"


def test_action_items_extra_keys_are_safely_ignored(monkeypatch):
    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            class Message:
                content = '{"summary":"Review done.","minutes":[],"decisions":[],"action_items":[{"task":"Check logs","owner":"Alice","deadline":"Friday","priority":"high"}]}'

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("meeting_assistant.llm._client", lambda: FakeClient())
    result = analyze_transcript("Alice: I'll check the logs by Friday.")

    assert len(result.action_items) == 1
    assert result.action_items[0].task == "Check logs"
    assert result.action_items[0].owner == "Alice"
    assert result.action_items[0].deadline == "Friday"

