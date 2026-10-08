"""Local speech-to-text using faster-whisper."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from meeting_assistant.security import safe_detail

SAMPLE_RATE = 16000


class TranscriptionError(RuntimeError):
    """Raised when audio cannot be decoded or contains no speech."""


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    # Word-level timestamps let speaker alignment split a segment at a speaker change.
    words: tuple[Word, ...] = ()


def load_audio(audio_path: Path) -> np.ndarray:
    """Decode any supported audio/video file once into 16 kHz mono float32 samples.

    The same array feeds both faster-whisper and pyannote, so both stages share one
    timeline and the file is only decoded once.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise TranscriptionError("The uploaded recording is empty or unreadable.")
    try:
        from faster_whisper.audio import decode_audio

        audio = decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)
    except Exception as exc:
        raise TranscriptionError(
            "Could not decode this recording. Make sure it is a valid audio file (or a video with an audio track). "
            f"Details: {safe_detail(exc)}"
        ) from exc
    if audio is None or audio.size == 0:
        raise TranscriptionError("The recording has no audio track or contains no audio samples.")
    if audio.size < SAMPLE_RATE // 2:
        raise TranscriptionError("The recording is too short (under half a second) to transcribe.")
    return audio


@lru_cache(maxsize=2)
def _load_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_segments(audio: Path | np.ndarray) -> list[TranscriptSegment]:
    if not isinstance(audio, np.ndarray):
        audio = load_audio(Path(audio))
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
        model_name = os.getenv("WHISPER_MODEL", "small")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16")
        model = _load_model(model_name, device, compute_type)
        segments, _info = model.transcribe(
            audio,
            language="en",
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=False,  # reduces repetition loops on long recordings
        )
        result = []
        for segment in segments:
            text = (segment.text or "").strip()
            if not text:
                continue
            words = tuple(
                Word(start=float(w.start), end=float(w.end), text=w.word)
                for w in (segment.words or [])
                if w.word and w.word.strip()
            )
            result.append(TranscriptSegment(start=float(segment.start), end=float(segment.end), text=text, words=words))
    except Exception as exc:
        raise TranscriptionError(f"Speech recognition failed. Details: {safe_detail(exc)}") from exc
    if not result:
        raise TranscriptionError("No speech could be recognized. Check that the recording is audible and try again.")
    return result


def transcribe(audio_path: Path) -> str:
    """Convenience helper returning concatenated transcript text."""
    segments = transcribe_segments(audio_path)
    return " ".join(s.text for s in segments)
