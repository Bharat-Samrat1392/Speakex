"""Streamlit interface for the AI-powered Meeting Assistant."""

from __future__ import annotations

import json
import os
import re
import tempfile
import html
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from meeting_assistant.exporters import record_as_markdown
from meeting_assistant.pipeline import MeetingPipeline, PipelineError
from meeting_assistant.schemas import MeetingRecord
from meeting_assistant.security import safe_detail

load_dotenv()


def _configured(name: str, placeholder: str) -> bool:
    value = os.getenv(name, "").strip().strip("'\"")
    return bool(value) and value != placeholder

st.set_page_config(page_title="Meeting Assistant", page_icon="🎙️", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS ---
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

header {visibility: hidden;}
footer {visibility: hidden;}

.hero-container {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
    padding: 4rem 2rem;
    border-radius: 20px;
    margin-bottom: 2rem;
    color: white;
    text-align: center;
    box-shadow: 0 10px 25px rgba(30, 58, 138, 0.1);
}
.hero-title {
    font-size: 3.5rem;
    font-weight: 700;
    margin-bottom: 1rem;
    letter-spacing: -0.02em;
    color: white;
}
.hero-subtitle {
    font-size: 1.25rem;
    font-weight: 300;
    color: #bfdbfe;
    max-width: 600px;
    margin: 0 auto;
}

[data-testid="stFileUploader"] {
    background: white;
    padding: 2rem;
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    transition: all 0.3s ease;
}
[data-testid="stFileUploader"]:hover {
    border-color: #93c5fd;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
}

.stButton>button[kind="primary"] {
    background-color: #2563eb !important;
    color: white !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
    border: none !important;
    transition: all 0.2s ease;
    box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
}
.stButton>button[kind="primary"]:hover {
    background-color: #1d4ed8 !important;
    box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);
    transform: translateY(-1px);
}

.stDownloadButton>button {
    background-color: white !important;
    color: #1e40af !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
    border: 1px solid #bfdbfe !important;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    width: 100%;
}
.stDownloadButton>button:hover {
    background-color: #f8fafc !important;
    border-color: #60a5fa !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    border-bottom: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: none;
    padding: 1rem 1.5rem;
    font-weight: 500;
    font-size: 1rem;
    color: #64748b;
    border-radius: 8px 8px 0 0;
    transition: all 0.2s ease;
    border-bottom: 3px solid transparent;
}
.stTabs [aria-selected="true"] {
    color: #1e3a8a !important;
    border-bottom: 3px solid #2563eb !important;
    background-color: transparent !important;
}

.transcript-container {
    background-color: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 2rem;
    margin-top: 1rem;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
    font-family: 'Inter', sans-serif;
    color: #334155;
    line-height: 1.8;
    max-height: 600px;
    overflow-y: auto;
}
.speaker-badge {
    background: #eff6ff;
    color: #1d4ed8;
    padding: 0.15rem 0.6rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 0.5rem;
    display: inline-block;
    border: 1px solid #bfdbfe;
    vertical-align: middle;
}
.timestamp-badge {
    color: #94a3b8;
    font-size: 0.75rem;
    font-family: monospace;
    margin-right: 0.5rem;
}

.record-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 2rem;
    margin-bottom: 1.5rem;
    margin-top: 1rem;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
}
.record-card-title {
    color: #0f172a;
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 0;
    margin-bottom: 1rem;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.record-card p, .record-card li {
    color: #334155;
    line-height: 1.7;
}
.record-card ul {
    margin-bottom: 0;
}
.action-item-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.action-item-task {
    font-weight: 500;
    color: #0f172a;
}
.action-item-meta {
    font-size: 0.875rem;
    color: #64748b;
    display: flex;
    gap: 1rem;
}
.action-item-owner {
    background: #dbeafe;
    color: #1e40af;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    font-weight: 600;
}
.action-item-deadline {
    background: #fef3c7;
    color: #92400e;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    font-weight: 600;
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --- HERO SECTION ---
st.markdown("""
<div class="hero-container">
    <div class="hero-title">Turn meetings into knowledge.</div>
    <div class="hero-subtitle">Upload your recording to automatically generate a faithful transcript, summary, and structured action items.</div>
</div>
""", unsafe_allow_html=True)

@st.cache_resource
def get_pipeline() -> MeetingPipeline:
    return MeetingPipeline()

with st.sidebar:
    st.header("Processing")
    st.caption("Speech recognition and speaker diarization run locally. Transcript refinement and meeting analysis use two separate LLM calls via Groq.")
    groq_ok = _configured("GROQ_API_KEY", "your_groq_api_key_here")
    hf_ok = _configured("HUGGINGFACE_TOKEN", "your_huggingface_token_here")
    st.markdown(f"{'✅' if groq_ok else '❌'} GROQ_API_KEY {'set' if groq_ok else 'missing'}")
    st.markdown(f"{'✅' if hf_ok else '❌'} HUGGINGFACE_TOKEN {'set' if hf_ok else 'missing'}")
    if not groq_ok:
        st.warning("Without GROQ_API_KEY only the raw transcript is produced.")
    if not hf_ok:
        st.warning("Without HUGGINGFACE_TOKEN the transcript has no speaker labels.")
    st.caption(f"Speech model: `{os.getenv('WHISPER_MODEL', 'small')}`")
    st.caption(f"Diarization model: `{os.getenv('DIARIZATION_MODEL', 'pyannote/speaker-diarization-community-1')}`")
    st.caption(f"Refinement model: `{os.getenv('REFINEMENT_MODEL', 'openai/gpt-oss-120b')}`")
    st.caption(f"Analysis model: `{os.getenv('ANALYSIS_MODEL', 'openai/gpt-oss-120b')}`")


upload = st.file_uploader(
    "Upload an English meeting recording",
    type=["wav", "mp3", "m4a", "mp4", "mpeg", "mpga", "webm", "ogg", "flac", "aac", "wma"],
    help="Common audio formats are supported. MP4 video files with an audio track are also accepted.",
)
# A new or removed upload must never keep showing the previous recording's results.
upload_id = None if upload is None else (upload.name, upload.size, getattr(upload, "file_id", None))
if st.session_state.get("upload_id") != upload_id:
    st.session_state["upload_id"] = upload_id
    st.session_state.pop("meeting_record", None)

process = st.button("Process recording", type="primary", disabled=upload is None, use_container_width=True)

if process:
    if upload is None or not upload.getvalue():
        st.error("The uploaded file is empty. Choose a readable recording and try again.")
    else:
        suffix = Path(upload.name).suffix.lower()
        if not suffix:
            st.error("The uploaded file has no file extension. Please upload a supported audio file.")
        else:
            with tempfile.TemporaryDirectory(prefix="meeting-assistant-") as tmp:
                audio_path = Path(tmp) / f"recording{suffix}"
                audio_path.write_bytes(upload.getvalue())
                status = st.status("Starting…", expanded=True)
                try:
                    pipeline = get_pipeline()
                    def update(message: str) -> None:
                        status.write(message)
                    record = pipeline.process(audio_path, source_filename=upload.name, on_status=update)
                    st.session_state["meeting_record"] = record.model_dump(mode="json")
                    if record.warnings:
                        status.update(label="Processing finished with warnings", state="complete", expanded=False)
                    else:
                        status.update(label="Processing complete", state="complete", expanded=False)
                        st.success("Done. See the tabs below for transcripts, the meeting record and downloads.")
                except PipelineError as exc:
                    status.update(label="Processing stopped", state="error", expanded=True)
                    st.error(str(exc))
                except Exception as exc:  # Streamlit should show a helpful message, not a traceback.
                    status.update(label="Processing stopped", state="error", expanded=True)
                    st.error(f"Unexpected processing error. {safe_detail(exc)}")

def render_transcript(text: str):
    escaped = html.escape(text)
    # Highlight speakers
    escaped = re.sub(
        r'(SPEAKER_\d+)', 
        r'<span class="speaker-badge">\1</span>', 
        escaped
    )
    # Highlight timestamps if present
    escaped = re.sub(
        r'(\[\d{2}:\d{2}\.\d{3} --&gt; \d{2}:\d{2}\.\d{3}\])',
        r'<span class="timestamp-badge">\1</span>',
        escaped
    )
    # Handle newlines
    html_out = escaped.replace('\n', '<br/>')
    st.markdown(f'<div class="transcript-container">{html_out}</div>', unsafe_allow_html=True)

payload = st.session_state.get("meeting_record")
if payload:
    record = MeetingRecord.model_validate(payload)
    st.markdown("<br/>", unsafe_allow_html=True)
    if record.warnings:
        for warning in record.warnings:
            st.warning(warning)

    st.markdown(f"<p style='color:#64748b; font-size:0.875rem;'>Speakers detected: {', '.join(record.speakers) if record.speakers else 'not available'} (anonymous labels from diarization)</p>", unsafe_allow_html=True)
    raw_tab, refined_tab, analysis_tab, export_tab = st.tabs(
        ["Raw transcript", "Refined transcript", "Meeting record", "Downloads"]
    )
    with raw_tab:
        render_transcript(record.raw_transcript)
    with refined_tab:
        render_transcript(record.refined_transcript)
    with analysis_tab:
        st.markdown(f'''
        <div class="record-card">
            <div class="record-card-title">📝 Summary</div>
            <p>{html.escape(record.analysis.summary) if record.analysis.summary else 'Analysis could not be produced.'}</p>
        </div>
        ''', unsafe_allow_html=True)
        
        minutes_html = "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in record.analysis.minutes) + "</ul>" if record.analysis.minutes else "<p style='color:#94a3b8;'>No minutes were extracted.</p>"
        st.markdown(f'''
        <div class="record-card">
            <div class="record-card-title">⏱️ Meeting minutes</div>
            {minutes_html}
        </div>
        ''', unsafe_allow_html=True)
        
        decisions_html = "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in record.analysis.decisions) + "</ul>" if record.analysis.decisions else "<p style='color:#94a3b8;'>No explicit decisions were identified.</p>"
        st.markdown(f'''
        <div class="record-card">
            <div class="record-card-title">🎯 Key decisions</div>
            {decisions_html}
        </div>
        ''', unsafe_allow_html=True)
        
        if record.analysis.action_items:
            items_html = ""
            for item in record.analysis.action_items:
                items_html += f'''
                <div class="action-item-box">
                    <div class="action-item-task">{html.escape(item.task)}</div>
                    <div class="action-item-meta">
                        <span class="action-item-owner">👤 {html.escape(item.owner)}</span>
                        <span class="action-item-deadline">📅 {html.escape(item.deadline)}</span>
                    </div>
                </div>
                '''
            st.markdown(f'''
            <div class="record-card">
                <div class="record-card-title">✅ Action items</div>
                {items_html}
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown('''
            <div class="record-card">
                <div class="record-card-title">✅ Action items</div>
                <p style='color:#94a3b8;'>No explicit action items were identified.</p>
            </div>
            ''', unsafe_allow_html=True)

    with export_tab:
        st.markdown('''
        <div class="record-card">
            <div class="record-card-title">📥 Download Meeting Record</div>
            <p>Export the transcripts and analysis for your records.</p>
        </div>
        ''', unsafe_allow_html=True)
        machine = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
        human = record_as_markdown(record)
        left, right = st.columns(2)
        with left:
            st.download_button("JSON (Machine-readable)", machine, file_name="meeting_record.json", mime="application/json", use_container_width=True)
        with right:
            st.download_button("Markdown (Human-readable)", human, file_name="meeting_record.md", mime="text/markdown", use_container_width=True)
        st.markdown("<p style='color:#94a3b8; font-size:0.875rem; text-align:center; margin-top:1rem;'>Both transcript versions are retained in each download.</p>", unsafe_allow_html=True)

st.markdown("<br/><hr style='border-color:#e2e8f0;'/><p style='color:#94a3b8; font-size:0.875rem; text-align:center;'>Outputs are model-assisted. Review the transcript and record before sharing or relying on them.</p>", unsafe_allow_html=True)
