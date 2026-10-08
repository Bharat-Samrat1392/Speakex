"""Local speaker diarization (pyannote.audio) and word-level speaker alignment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np

from meeting_assistant.security import safe_detail
from meeting_assistant.transcription import SAMPLE_RATE, TranscriptionError, TranscriptSegment, load_audio

UNKNOWN_SPEAKER = "SPEAKER_UNKNOWN"
# A word with no overlapping speaker turn may borrow the nearest turn's speaker only
# if that turn is this close (seconds). Beyond that we don't guess.
MAX_GAP_SECONDS = 1.0


class DiarizationError(RuntimeError):
    """Raised when speaker diarization fails."""


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class SpeakerSegment:
    start: float
    end: float
    speaker: str
    text: str


def resolve_device(requested: str | None) -> str:
    """Use CUDA only when asked for (or 'auto') AND actually usable; otherwise CPU."""
    import torch

    requested = (requested or "auto").strip().lower()
    cuda_ok = False
    try:
        cuda_ok = torch.cuda.is_available()
    except Exception:
        cuda_ok = False
    if requested in ("auto", "") or requested.startswith("cuda"):
        return (requested if requested.startswith("cuda") else "cuda") if cuda_ok else "cpu"
    return "cpu"


@lru_cache(maxsize=1)
def _load_pipeline(token: str, model_id: str, device_str: str):
    import torch
    from pyannote.audio import Pipeline

    try:
        pipeline = Pipeline.from_pretrained(model_id, token=token)
    except Exception as exc:
        text = str(exc).lower()
        if any(k in text for k in ("401", "403", "gated", "unauthorized", "access", "token")):
            raise DiarizationError(
                f"Could not download '{model_id}' from Hugging Face. Check HUGGINGFACE_TOKEN and make sure you "
                f"accepted the model's user conditions at https://huggingface.co/{model_id}."
            ) from exc
        raise DiarizationError(f"Could not load the pyannote pipeline. Details: {safe_detail(exc)}") from exc
    if pipeline is None:
        raise DiarizationError(
            f"Could not load '{model_id}'. Check that HUGGINGFACE_TOKEN has access to this repository."
        )
    if device_str != "cpu":
        try:
            pipeline.to(torch.device(device_str))
        except Exception:
            pipeline.to(torch.device("cpu"))
    return pipeline


def diarize(audio: Path | np.ndarray) -> list[SpeakerTurn]:
    """Run speaker diarization on a file path or a 16 kHz mono float32 array."""
    import torch
    from dotenv import load_dotenv

    load_dotenv(override=True)
    token = os.getenv("HUGGINGFACE_TOKEN", "").strip().strip("'\"")
    if not token or token == "your_huggingface_token_here":
        raise DiarizationError("HUGGINGFACE_TOKEN is missing. Add a Hugging Face token to .env to enable speaker diarization.")

    model_id = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1")
    device_str = resolve_device(os.getenv("DIARIZATION_DEVICE", "auto"))
    pipeline = _load_pipeline(token, model_id, device_str)

    if not isinstance(audio, np.ndarray):
        try:
            audio = load_audio(Path(audio))
        except TranscriptionError as exc:
            raise DiarizationError(str(exc)) from exc
    waveform = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)

    try:
        output = pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE})
    except Exception as exc:
        raise DiarizationError(f"Diarization inference failed. Details: {safe_detail(exc)}") from exc

    # pyannote 4 returns an object with both views; the exclusive one (one speaker at a time)
    # is the right one for assigning transcript words. Don't use `or`: an empty Annotation is falsy.
    annotation = getattr(output, "exclusive_speaker_diarization", None)
    if annotation is None:
        annotation = getattr(output, "speaker_diarization", None)
    if annotation is None:
        annotation = output
    turns = [
        SpeakerTurn(start=float(turn.start), end=float(turn.end), speaker=str(speaker))
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: (t.start, t.end))
    return turns


def _speaker_for_span(start: float, end: float, turns: Sequence[SpeakerTurn]) -> str | None:
    """Speaker with the largest temporal overlap; else a turn within MAX_GAP_SECONDS; else None."""
    overlaps: dict[str, float] = {}
    for turn in turns:
        overlap = min(end, turn.end) - max(start, turn.start)
        if overlap > 0:
            overlaps[turn.speaker] = overlaps.get(turn.speaker, 0.0) + overlap
    if overlaps:
        return max(overlaps.items(), key=lambda item: item[1])[0]
    best, best_gap = None, MAX_GAP_SECONDS
    for turn in turns:
        gap = start - turn.end if turn.end <= start else turn.start - end
        if gap <= best_gap:
            best, best_gap = turn.speaker, gap
    return best


def assign_speakers(
    segments: Sequence[TranscriptSegment],
    speaker_turns: Sequence[SpeakerTurn],
) -> list[SpeakerSegment]:
    """Align faster-whisper output with pyannote turns by temporal overlap.

    Words (when word timestamps exist) are assigned individually, so a segment that spans a
    speaker change is split at the change instead of being given wholesale to one speaker.
    Transcript text is never altered; unlabelled stretches become SPEAKER_UNKNOWN.
    """
    units: list[tuple[float, float, str, str | None]] = []  # start, end, text, speaker
    for seg in segments:
        pieces = [(w.start, w.end, w.text) for w in seg.words] or [(seg.start, seg.end, seg.text)]
        labelled = [(s, e, t, _speaker_for_span(s, e, speaker_turns)) for s, e, t in pieces]
        # Words inside a pause between turns inherit a neighbour's speaker within the same segment.
        for i, (s, e, t, spk) in enumerate(labelled):
            if spk is None:
                prev = next((x[3] for x in reversed(labelled[:i]) if x[3]), None)
                nxt = next((x[3] for x in labelled[i + 1 :] if x[3]), None)
                labelled[i] = (s, e, t, prev or nxt)
        # Smooth one-word blips (A A B A -> A A A A): a lone short word is more likely a boundary error.
        for i in range(1, len(labelled) - 1):
            s, e, t, spk = labelled[i]
            before, after = labelled[i - 1][3], labelled[i + 1][3]
            if before and before == after and spk != before and (e - s) < 0.6:
                labelled[i] = (s, e, t, before)
        units.extend(labelled)

    merged: list[list] = []
    for start, end, text, speaker in units:
        speaker = speaker or UNKNOWN_SPEAKER
        if merged and merged[-1][2] == speaker:
            merged[-1][1] = end
            merged[-1][3].append(text)
        else:
            merged.append([start, end, speaker, [text]])
    result = []
    for start, end, speaker, texts in merged:
        joined = "".join(t if t[:1].isspace() else " " + t for t in texts)
        text = " ".join(joined.split())
        if text:
            result.append(SpeakerSegment(start=round(start, 2), end=round(end, 2), speaker=speaker, text=text))
    return result


def format_speaker_transcript(speaker_segments: Sequence[SpeakerSegment]) -> str:
    return "\n\n".join(f"{s.speaker}: {s.text}" for s in speaker_segments)


def align_segments_with_speakers(
    segments: Sequence[TranscriptSegment],
    speaker_turns: Sequence[SpeakerTurn],
) -> str:
    """Speaker-labelled transcript text (one paragraph per speaker turn)."""
    return format_speaker_transcript(assign_speakers(segments, speaker_turns))
