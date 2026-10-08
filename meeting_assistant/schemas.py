"""Validated machine-readable meeting record models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    task: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    deadline: str = Field(min_length=1)

    @field_validator("task", "owner", "deadline")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field must not be blank")
        return value


class Analysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str = ""
    minutes: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)

    @field_validator("minutes", "decisions")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class TranscriptTurn(BaseModel):
    """One speaker turn of the raw transcript with its timestamps (seconds)."""

    model_config = ConfigDict(extra="forbid")
    start: float
    end: float
    speaker: str
    text: str


class MeetingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.1"] = "1.1"
    source_filename: str
    speakers: list[str] = Field(default_factory=list)
    raw_transcript: str
    raw_segments: list[TranscriptTurn] = Field(default_factory=list)
    refined_transcript: str
    analysis: Analysis = Field(default_factory=Analysis)
    warnings: list[str] = Field(default_factory=list)
