# Meeting Assistant — Decisions and Actions (Draft)

> **Status:** Working draft for owner review. This record uses only the supplied conversation preview and the cached recent turns of the referenced conversation. The earlier turn-by-turn technical history was not included in that cached portion. Where facts are absent, they are left as questions rather than inferred.
>
> **Project / event:** INTER-IIT is mentioned; confirm exact event and track.  
> **Owner:** TODO / CONFIRM  
> **Last reported status:** Windows verification and submission ZIP audit completed; recommendation was to freeze the build and move to demonstration/submission.

## How to read this draft

- **Recorded** items were stated in the conversation excerpt.
- **TODO / CONFIRM** marks missing or ambiguous details to fill in.
- Test and runtime results describe the reported verification session, not a guarantee for other machines, recordings, dependency versions, or API conditions.

## Requirements known from the conversation

The recent conversation says the submission needs a source package containing the implementation, prompts/model instructions, tests, configuration template, dependencies, and documentation. It also says the problem statement requires a **shareable recording demonstrating the system and its outputs**. The source ZIP should not carry the recording; `clip_10.mp4` and generated meeting records were suggested as separate demo/supporting assets. The suggested demo shows application launch, upload, processing, raw and refined transcripts, meeting record, decisions/action items, and JSON/Markdown downloads.

**TODO / CONFIRM:** Add the exact official problem statement, judging criteria, required deliverable formats, limits, and wording. Those were not present in the cached excerpt; the items above are not a complete requirements specification.

## Chronological and technical decision record

### Initial OpenAI setup and environment mismatch

- **Action / decision:** An initial OpenAI-based setup was attempted; project history later moved from OpenAI to Groq. The requested history also identifies an environment mismatch.
- **Why:** Exact cause/effect and rationale are missing from the available conversation excerpt. Do not assume the provider migration alone fixed the environment mismatch.
- **Alternatives:** OpenAI was the initial path; Groq became the reported final provider. No other alternatives are evidenced.
- **Technical details / evidence:** TODO / CONFIRM initial SDK, model, error text, commands, environment, and which component was affected. Final verification later lists Groq and both LLM stages as working.
- **TODO / CONFIRM:** Add the initial failure, diagnosis, and why OpenAI was replaced.

### Runtime environment stabilization

- **Action / decision:** Final reported run used Windows `.venv`, Python **3.13.5**, `pyannote.audio` **4.0.7**, Faster-Whisper, Streamlit, and Groq.
- **Why:** The project history identifies an environment mismatch; a usable local runtime was needed for end-to-end audio verification.
- **Alternatives:** TODO / CONFIRM. No specific rejected OS/Python alternative is in the excerpt.
- **Verification:** The conversation reports successful processing on the user's actual Windows machine.
- **TODO / CONFIRM:** Record original mismatch, setup commands, full pinned dependency list, Python/pytest versions, device/hardware, and whether the environment was rebuilt from scratch. Exact versions for most packages are not in the excerpt.

### OpenAI-to-Groq migration and two-stage LLM design

- **Action / decision:** The reported final workflow uses Groq for two logical LLM stages: **LLM #1** refines the transcript; **LLM #2** analyzes the meeting.
- **Why:** The workflow needs transcript refinement and structured meeting outputs. The reason for choosing Groq over OpenAI is not recorded in the supplied excerpt.
- **Alternatives:** OpenAI was initially attempted; no model/provider benchmark or other alternatives are recorded.
- **Technical details:** `prompts/refine_transcript.txt` and `prompts/analyze_meeting.txt` are included in the package. Exact model identifiers, SDK version, env-var names, request parameters, token limits, retry logic, and validation behavior are TODO / CONFIRM. Do not put secret values in this document.
- **Verification:** Both LLM stages reportedly completed during the successful `clip_10.mp4` run. Provider/API errors were reported not to expose keys.
- **TODO / CONFIRM:** Add migration rationale and safe variable names (not credential values).

### Speech recognition model

- **Decision:** `WHISPER_MODEL=tiny` is the currently verified configuration and was retained in the frozen build.
- **Why:** It was the configuration used in the reported successful run. A last-minute model change could affect processing time, memory, CPU load, and outputs.
- **Alternative:** `small` was considered as a possible transcription-quality improvement but **was not adopted** in the final frozen build; the conversation recommends only considering it after separate testing.
- **Technical details:** Faster-Whisper is the reported STT component. Exact version, compute type, device, language configuration, and configuration location are TODO / CONFIRM.
- **Evidence:** The `tiny` configuration produced a raw transcript in the reported Windows run on `clip_10.mp4`.

### Diarization and speaker alignment

- **Action / decision:** Pyannote Community-1 diarization and speaker alignment were added to the pipeline.
- **Why:** The project history identifies diarization addition and alignment fixes; the workflow produces speaker-attributed transcript segments.
- **Technical details:** Reported `pyannote.audio` version: **4.0.7**. The final described pipeline is Faster-Whisper STT → raw transcript → Pyannote Community-1 → speaker alignment → LLM #1 refinement → LLM #2 analysis. Exact model revision, auth setup, timestamp matching algorithm, thresholds, and alignment bug/fix are unknown.
- **Verification:** The sample run reported three anonymous labels: `SPEAKER_00`, `SPEAKER_01`, and `SPEAKER_02`. Reviewed timestamp examples included `SPEAKER_00` from 0–24.4 seconds and `SPEAKER_02` from 25.36–27.18 seconds.
- **TODO / CONFIRM:** Document exact model identifier/revision and alignment fix. Three speakers describes this clip's reported output, not a fixed system limit.

### Security and conservative extraction safeguards

- **Action / decision:** Security and output safeguards were implemented/reported.
- **Recorded behaviors:** Speaker labels are not replaced by invented names; suggestions are not automatically treated as decisions; unconfirmed tasks are not automatically assigned; missing owners/deadlines can remain unspecified; provider/API errors do not expose keys. Stale results are cleared when recordings change.
- **Why:** These behaviors limit unsupported attribution, assignment, or disclosure and prevent results from a previous recording being mistaken for current results. Exact original defects and rationale are not available.
- **Technical evidence:** `meeting_assistant/security.py` exists in the reported ZIP; `.env.example` and `.gitignore` are included. `tests/test_safeguards.py` is present. The archive audit reported no `.env` at its top level.
- **TODO / CONFIRM:** Describe the security bug(s), implementation details, secret-loading and redaction behavior, and specific test assertions. Never add actual tokens or keys.

### LLM #1 — transcript refinement

- **Decision:** A distinct transcript refinement stage uses `prompts/refine_transcript.txt`.
- **Why / tradeoff:** It corrects clear errors while remaining conservative when speech is uncertain, preferring uncertainty over invented words.
- **Verification:** The reviewed output corrected examples such as “earth hotels” → “Earth Hotels” and “bikini Berlin” → “Bikini Berlin.” Other phrases remained rough (the conversation cites “J1 pair,” “Salagra? Chalagra?,” “Jabba, B-3,” “non-mutants,” and “non-utiliar”). The review accepted this as preferable to confident guessing.
- **TODO / CONFIRM:** Exact model, prompt policy, input/output schema, and whether speaker/timestamp metadata is passed into the LLM are unknown.

### LLM #2 — meeting analysis

- **Decision:** A second stage uses `prompts/analyze_meeting.txt` to produce summary, minutes, decisions, and action items.
- **Why:** Meeting analysis is separated from transcript refinement in the final architecture shown in the conversation.
- **Verification:** For the demonstrated clip, the output said “No explicit decisions identified” and “No explicit action items identified”; these matched empty `decisions` and `action_items` arrays in JSON.
- **TODO / CONFIRM:** Exact model, schema, validation/retry rules, and any comparison with a one-stage design are not documented in the excerpt.

### Exports and UI

- **Decision:** The application provides JSON and Markdown exports and corresponding download actions.
- **Technical details:** Reviewed JSON reported `schema_version: "1.1"`, speakers, raw transcript, timestamped `raw_segments`, refined transcript, summary/minutes, decisions, action items, and warnings. Markdown contained the speaker list, summary, minutes, decisions, action items, raw transcript, and refined transcript.
- **Verification:** Both files downloaded successfully (`meeting_record.md`, reported 7 KB; `meeting_record.json`, reported 10 KB) and were reviewed as valid and consistent with the UI. Sizes are sample-specific, not requirements. Both downloads were reported working end to end.
- **UI action:** Stale results are cleared when a recording changes. Streamlit was part of the reported environment. Exact UI bug and state-management fix are not included.
- **TODO / CONFIRM:** Confirm schema version, exact UI fixes, export compatibility policy, and the interaction used to test stale-result clearing.

### Tests and debugging/upgrades

- **Action:** The test suite was run; the user-request context also identifies debugging fixes and upgrades, but individual earlier issues are absent from the cached excerpt.
- **Test files in the reported ZIP:** `tests/test_pipeline_e2e.py`, `tests/test_safeguards.py`, and `tests/test_schemas_and_exports.py`.
- **Evidence:** **21 passed in 2.96s** (also summarized as 21/21). This is the reported run result only.
- **TODO / CONFIRM:** Add exact command, run date, pytest version, skipped tests, and chronological individual bugs/fixes/upgrades. The excerpt does not state package upgrade history beyond Python 3.13.5 and pyannote.audio 4.0.7.

## End-to-end verification record

The conversation reports these results from the user's actual Windows machine. They are verification results for that run, not universal guarantees.

| Area | Reported result |
|---|---|
| Runtime | Windows `.venv`; Python 3.13.5 |
| Key package | `pyannote.audio` 4.0.7; Faster-Whisper, Streamlit, Groq also reported |
| STT setting | `WHISPER_MODEL=tiny` |
| Input | `clip_10.mp4` |
| Audio pipeline | Real audio processing, raw transcription, diarization, speaker alignment |
| Speakers | Three anonymous labels reported for this clip |
| LLM stages | Transcript refinement and meeting analysis both completed |
| Outputs | Summary, minutes, decisions and action items; no explicit decisions/actions found in this clip |
| Downloads | JSON and Markdown reportedly downloaded and inspected |
| Tests | 21/21 passed; reported time 2.96 seconds |

**TODO / CONFIRM:** Add run timestamp, machine specs, exact app launch/process command, exact model identifiers, and whether the run began in a fresh session.

## Final package and freeze decisions

### ZIP structure and hygiene

The reported `meeting_assistant_submission.zip` top level contained:

```text
meeting_assistant/
prompts/
tests/
.env.example
.gitignore
app.py
README.md
requirements.txt
```

Reported implementation files:

```text
meeting_assistant/__init__.py
meeting_assistant/diarization.py
meeting_assistant/exporters.py
meeting_assistant/llm.py
meeting_assistant/pipeline.py
meeting_assistant/schemas.py
meeting_assistant/security.py
meeting_assistant/transcription.py
```

Prompts: `prompts/analyze_meeting.txt`, `prompts/refine_transcript.txt`. Tests are listed above.

- **Decision:** Keep the source ZIP focused on project files; exclude `.env`, `.venv/`, recordings, caches, compiled Python files, and junk.
- **Why:** The conversation cites repository-size/security hygiene and the need to provide source and prompts. It says the recording should be shared separately.
- **Verification:** Top-level audit reported no `.env`, `.venv/`, `recordings/`, `__pycache__/`, or `.pytest_cache/`. Folder screenshots showed expected Python modules/prompts/tests and no `__pycache__`, `.pyc`, or junk files.
- **TODO / CONFIRM:** This was a visual archive audit, not a recorded checksum or automated recursive scan. Confirm final ZIP path, timestamp, backup, and checksum.

### Demo assets and freeze

- **Decision:** Keep `clip_10.mp4`, `meeting_record.json`, and `meeting_record.md` available separately as demo/supporting assets. The suggested demo sequence is launch → upload → process → show raw transcript → refined transcript → meeting record → decisions/action items → JSON and Markdown downloads.
- **Why:** A shareable demo recording is stated as a problem requirement; keeping media outside the source ZIP also preserves package hygiene.
- **Decision:** Freeze the current verified build. Avoid last-minute code changes, package upgrades, refactoring, or changing `tiny` to `small` without a specific need and fresh verification.
- **Why:** The existing build was reported working through real audio, diarization, both LLM stages, outputs, downloads, tests, and ZIP audit. Model/dependency changes may affect runtime and results.
- **TODO / CONFIRM:** Confirm the demo recording exists, its share location and permissions/privacy, final submission portal requirements, final ZIP backup/checksum, freeze owner/date, and criteria for reopening the build.

## Open questions for finalization

1. What is the exact official problem statement and full deliverable checklist?
2. What precisely failed in the original OpenAI setup, and what environment mismatch was diagnosed?
3. Why was Groq chosen? What exact Groq model IDs and SDK/package versions were used?
4. What exact requirements/package versions are frozen? Which upgrades happened and why?
5. What were the specific security, alignment, and UI bugs and their fixes?
6. What Pyannote model identifier/revision and authentication configuration were used?
7. What exact command and test environment produced the 21 passing tests? Any skipped/integration tests?
8. What machine/hardware and runtime characteristics applied to the `clip_10.mp4` run?
9. Is the ZIP audited here the exact file intended for submission? Was a backup/checksum made?
10. Has the shareable demo recording been made, reviewed, and stored with the output assets?
11. Should the rough transcript examples remain in the final record, or should they be generalized?

## Final checklist

- [x] Reported Windows end-to-end verification: Python 3.13.5, pyannote.audio 4.0.7.
- [x] Reported `WHISPER_MODEL=tiny` as the verified frozen setting; `small` considered but not adopted.
- [x] Reported successful `clip_10.mp4` processing, three anonymous speakers, both LLM stages, and meeting outputs.
- [x] Reported JSON/Markdown downloads and consistency review.
- [x] Reported 21/21 tests passing (2.96 seconds).
- [x] Reported clean ZIP structure and folder-level cache/junk inspection.
- [ ] Confirm exact official requirements and fill earlier technical/debugging history.
- [ ] Confirm ZIP backup/checksum and location.
- [ ] Confirm shareable demo recording and asset location.
- [ ] Resolve TODO / CONFIRM items before treating this as a final audit trail.

**Comment for finalization:** The recent cached conversation confirms the final verification and packaging in detail, but not the earlier turn-by-turn debugging history. Add those details from the full project record or source artifacts before calling this a complete historical record.
