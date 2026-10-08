"""Human-readable export rendering."""

from __future__ import annotations

from meeting_assistant.schemas import MeetingRecord


def record_as_markdown(record: MeetingRecord) -> str:
    analysis = record.analysis
    lines = [
        "# Meeting record",
        "",
        f"- Source file: {record.source_filename}",
        f"- Speakers detected: {', '.join(record.speakers) if record.speakers else 'Not available'}",
        "- Speaker labels are anonymous diarization labels, not identified people.",
        "",
        "## Concise summary",
        analysis.summary or "Analysis unavailable.",
        "",
        "## Meeting minutes",
        *([f"- {item}" for item in analysis.minutes] or ["- None identified."]),
        "",
        "## Key decisions",
        *([f"- {item}" for item in analysis.decisions] or ["- No explicit decisions identified."]),
        "",
        "## Action items",
    ]
    if analysis.action_items:
        lines.extend(["| Task | Owner | Deadline |", "|---|---|---|"])
        for item in analysis.action_items:
            task, owner, deadline = (value.replace("|", "\\|") for value in (item.task, item.owner, item.deadline))
            lines.append(f"| {task} | {owner} | {deadline} |")
    else:
        lines.append("- No explicit action items identified.")
    lines.extend(["", "## Raw transcript", record.raw_transcript, "", "## Refined transcript", record.refined_transcript])
    if record.warnings:
        lines.extend(["", "## Processing notes", *[f"- {item}" for item in record.warnings]])
    return "\n".join(lines) + "\n"
