"""End-to-end meeting processing orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from meeting_assistant.diarization import (
    DiarizationError,
    assign_speakers,
    diarize,
    format_speaker_transcript,
)
from meeting_assistant.llm import LLMError, analyze_transcript, refine_transcript_checked
from meeting_assistant.schemas import Analysis, MeetingRecord, TranscriptTurn
from meeting_assistant.security import redact, safe_detail
from meeting_assistant.transcription import (
    TranscriptionError,
    load_audio,
    transcribe_segments,
)


class PipelineError(RuntimeError):
    """A user-displayable processing failure."""


class MeetingPipeline:
    def process(
        self,
        audio_path: Path,
        *,
        source_filename: str,
        on_status: Callable[[str], None] | None = None,
    ) -> MeetingRecord:
        report = on_status or (lambda _message: None)
        warnings: list[str] = []
        try:
            report("1/5 Decoding audio and transcribing with faster-whisper…")
            audio = load_audio(Path(audio_path))  # decoded once, shared by STT and diarization
            segments = transcribe_segments(audio)

            report("2/5 Running speaker diarization with pyannote Community-1…")
            try:
                turns = diarize(audio)
                speaker_segments = assign_speakers(segments, turns)
                raw = format_speaker_transcript(speaker_segments)
                raw_segments = [TranscriptTurn(**vars(s)) for s in speaker_segments]
            except DiarizationError as exc:
                # Keep going without speaker labels rather than failing the whole meeting.
                raw = "\n\n".join(s.text for s in segments)
                raw_segments = [
                    TranscriptTurn(start=round(s.start, 2), end=round(s.end, 2), speaker="SPEAKER_UNKNOWN", text=s.text)
                    for s in segments
                ]
                warnings.append(f"Speaker diarization unavailable; transcript has no speaker labels. {redact(exc)}")

            report("3/5 Refining terminology and dialogue with Groq LLM #1…")
            try:
                refined, refine_warnings = refine_transcript_checked(raw)
                warnings.extend(refine_warnings)
            except LLMError as exc:
                refined = raw
                warnings.append(f"Transcript refinement unavailable; the raw transcript is shown unchanged. {redact(exc)}")

            report("4/5 Generating summary, minutes, decisions, and action items with Groq LLM #2…")
            try:
                analysis = analyze_transcript(refined)
            except LLMError as exc:
                analysis = Analysis()
                warnings.append(f"Meeting analysis unavailable; no decisions or action items were inferred. {redact(exc)}")

            report("5/5 Packaging meeting records and downloads…")
            speakers = sorted({t.speaker for t in raw_segments if t.speaker != "SPEAKER_UNKNOWN"})
            return MeetingRecord(
                source_filename=source_filename,
                speakers=speakers,
                raw_transcript=raw,
                raw_segments=raw_segments,
                refined_transcript=refined,
                analysis=analysis,
                warnings=warnings,
            )
        except TranscriptionError as exc:
            raise PipelineError(redact(exc)) from exc
        except Exception as exc:
            raise PipelineError(f"Pipeline processing failed. {safe_detail(exc)}") from exc
