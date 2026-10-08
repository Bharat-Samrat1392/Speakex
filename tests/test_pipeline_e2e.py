import json
from pathlib import Path
import pytest

from meeting_assistant.diarization import (
    SpeakerTurn,
    align_segments_with_speakers,
)
from meeting_assistant.pipeline import MeetingPipeline
from meeting_assistant.schemas import ActionItem, Analysis, MeetingRecord
from meeting_assistant.exporters import record_as_markdown
from meeting_assistant.transcription import TranscriptSegment
import meeting_assistant.llm as llm_module


def test_align_segments_with_speakers_logic():
    # 1. Test overlap matching and consecutive merge
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="Hello everyone."),
        TranscriptSegment(start=2.1, end=4.0, text="Let's begin the meeting."),
        TranscriptSegment(start=4.5, end=6.5, text="I have the updates."),
        TranscriptSegment(start=7.0, end=9.0, text="Great, let's hear them."),
    ]
    speaker_turns = [
        SpeakerTurn(start=0.0, end=4.2, speaker="SPEAKER_00"),
        SpeakerTurn(start=4.3, end=6.8, speaker="SPEAKER_01"),
        SpeakerTurn(start=6.9, end=9.5, speaker="SPEAKER_00"),
    ]

    aligned = align_segments_with_speakers(segments, speaker_turns)
    expected = (
        "SPEAKER_00: Hello everyone. Let's begin the meeting.\n\n"
        "SPEAKER_01: I have the updates.\n\n"
        "SPEAKER_00: Great, let's hear them."
    )
    assert aligned == expected


def test_align_segments_maximum_overlap():
    # Segment spans 1.0 to 5.0 (length 4s)
    # Speaker 0 overlaps 1.0-2.0 (1s)
    # Speaker 1 overlaps 2.0-5.0 (3s) -> Speaker 1 has maximum overlap
    segments = [TranscriptSegment(start=1.0, end=5.0, text="Overlapping speech.")]
    turns = [
        SpeakerTurn(start=0.0, end=2.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=2.0, end=6.0, speaker="SPEAKER_01"),
    ]
    aligned = align_segments_with_speakers(segments, turns)
    assert aligned == "SPEAKER_01: Overlapping speech."


def test_align_segments_fallback_when_no_overlap():
    # Segment with no overlapping speaker turns falls back to nearest
    segments = [TranscriptSegment(start=10.0, end=12.0, text="Speaking in a gap.")]
    turns = [
        SpeakerTurn(start=1.0, end=3.0, speaker="SPEAKER_00"),
        SpeakerTurn(start=15.0, end=17.0, speaker="SPEAKER_01"),
    ]
    # Nearest turns are 3s and 7s away: too far to attribute reliably, so no speaker is guessed.
    aligned = align_segments_with_speakers(segments, turns)
    assert aligned == "SPEAKER_UNKNOWN: Speaking in a gap."

    # A short pause (<= 1s) next to a turn is attributed to that turn.
    near = [TranscriptSegment(start=3.4, end=4.0, text="Right.")]
    assert align_segments_with_speakers(near, turns) == "SPEAKER_00: Right."


def test_segment_spanning_speaker_change_is_split_by_word_timestamps():
    from meeting_assistant.transcription import Word

    words = (
        Word(0.0, 0.4, " Can"), Word(0.4, 0.8, " you"), Word(0.8, 1.4, " deploy?"),
        Word(1.6, 2.0, " Yes,"), Word(2.0, 2.3, " I"), Word(2.3, 2.9, " will."),
    )
    segments = [TranscriptSegment(start=0.0, end=2.9, text="Can you deploy? Yes, I will.", words=words)]
    turns = [SpeakerTurn(0.0, 1.5, "SPEAKER_00"), SpeakerTurn(1.5, 3.0, "SPEAKER_01")]
    assert align_segments_with_speakers(segments, turns) == "SPEAKER_00: Can you deploy?\n\nSPEAKER_01: Yes, I will."


def test_end_to_end_pipeline_with_mocked_llm_and_diarization(monkeypatch):
    fake_segments = [
        TranscriptSegment(start=0.0, end=3.0, text="Welcome everyone."),
        TranscriptSegment(start=3.1, end=6.0, text="We're opening five hotels in 18 months."),
        TranscriptSegment(start=6.5, end=9.0, text="I will prepare the pitch by Friday."),
    ]
    fake_turns = [
        SpeakerTurn(start=0.0, end=6.2, speaker="SPEAKER_00"),
        SpeakerTurn(start=6.3, end=9.5, speaker="SPEAKER_01"),
    ]

    monkeypatch.setattr("meeting_assistant.pipeline.load_audio", lambda _p: "decoded-audio")
    monkeypatch.setattr("meeting_assistant.pipeline.transcribe_segments", lambda _p: fake_segments)
    monkeypatch.setattr("meeting_assistant.pipeline.diarize", lambda _p: fake_turns)

    refined_mock = (
        "SPEAKER_00: Welcome everyone. We're opening five hotels in 18 months.\n\n"
        "SPEAKER_01: I will prepare the pitch by Friday."
    )
    analysis_mock = {
        "summary": "Meeting discussing hotel openings and pitch preparation.",
        "minutes": [
            "SPEAKER_00 announced opening five hotels in 18 months.",
            "SPEAKER_01 committed to pitch preparation.",
        ],
        "decisions": [
            "Open five hotels in 18 months.",
        ],
        "action_items": [
            {
                "task": "Prepare the pitch",
                "owner": "SPEAKER_01",
                "deadline": "Friday",
            },
            {
                "task": "Review floor plans",
                "owner": "none",
                "deadline": "TBD",
            },
        ],
    }

    class FakeRefineChoice:
        message = type("Msg", (), {"content": refined_mock})()

    class FakeAnalysisChoice:
        message = type("Msg", (), {"content": json.dumps(analysis_mock)})()

    class FakeCompletions:
        @staticmethod
        def create(model, messages, **kwargs):
            if "stage 1" in messages[0]["content"].lower():
                return type("Resp", (), {"choices": [FakeRefineChoice()]})()
            return type("Resp", (), {"choices": [FakeAnalysisChoice()]})()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_module, "_client", lambda: FakeClient())

    pipeline = MeetingPipeline()
    record = pipeline.process(Path("dummy.wav"), source_filename="meeting.wav")

    # Verify speaker-labelled raw transcript
    assert "SPEAKER_00: Welcome everyone. We're opening five hotels in 18 months." in record.raw_transcript
    assert "SPEAKER_01: I will prepare the pitch by Friday." in record.raw_transcript

    # Verify speaker-labelled refined transcript
    assert record.refined_transcript == refined_mock
    assert len(record.warnings) == 0

    # Verify analysis attributes owner correctly
    assert record.analysis.action_items[0].owner == "SPEAKER_01"
    assert record.analysis.action_items[0].deadline == "Friday"
    assert record.analysis.action_items[1].owner == "Unspecified"
    assert record.analysis.action_items[1].deadline == "Unspecified"

    # Verify markdown export retains speaker labels and attributes
    md_export = record_as_markdown(record)
    assert "## Raw transcript" in md_export
    assert "SPEAKER_00:" in md_export
    assert "SPEAKER_01:" in md_export
    assert "SPEAKER_01" in md_export
    assert "Friday" in md_export

    # Verify JSON export retains speaker labels
    json_export = json.dumps(record.model_dump(mode="json"), indent=2)
    parsed_json = json.loads(json_export)
    assert "SPEAKER_00:" in parsed_json["raw_transcript"]
    assert parsed_json["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert parsed_json["raw_segments"][1]["speaker"] == "SPEAKER_01"
    assert parsed_json["analysis"]["action_items"][0]["owner"] == "SPEAKER_01"
