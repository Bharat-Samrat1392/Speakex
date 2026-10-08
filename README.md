# Speakex – AI-powered Meeting Assistant

Upload an English meeting recording and get back:

- a raw transcript with speaker labels (straight from speech-to-text)
- a cleaned-up (refined) transcript with the same speaker labels
- a short summary, meeting minutes, key decisions and action items
- downloads as Markdown (for people) and JSON (for programs)

Speech-to-text and speaker diarization run on your own machine. The two language-model steps run on Groq. The UI is a modern, responsive React frontend.

## Architecture

Speakex is built in two layers:

**1. FastAPI Backend (Python)**
The ML pipeline runs completely asynchronously in a FastAPI backend. 
```text
audio / video file
  ↓  decoded once to 16 kHz mono
faster-whisper  →  timestamped segments + word timestamps
  ↓
pyannote/speaker-diarization-community-1  →  who spoke when
  ↓
alignment by time overlap (word level)  →  RAW transcript: SPEAKER_00: ..., SPEAKER_01: ...
  ↓
Groq LLM #1 (refine)  →  REFINED transcript, same speakers
  ↓
Groq LLM #2 (analyze)  →  summary, minutes, decisions, action items (validated JSON)
  ↓
JSON & Markdown output
```

**2. React Frontend (TypeScript + Vite)**
The modern frontend (Speakex) connects to the API layer, replacing the original Streamlit fallback.
```text
Lovable Frontend (React / Vite)
  ↓ HTTP Multipart Upload
FastAPI Layer (POST /api/process)
  ↓ Async Task Queue
Background ML Pipeline
  ↓ Poll (GET /api/status/{job_id})
Frontend Status UI
  ↓ Retrieve (GET /api/result/{job_id})
Frontend Meeting Record UI
```

A few details worth knowing:
- **Speaker alignment:** Every word is given to the diarization speaker it overlaps most. If one Whisper segment covers two people talking, it gets split where the speaker changes.
- **Speaker names:** Labels are anonymous (`SPEAKER_00`, `SPEAKER_01`). The LLMs aren't allowed to turn them into names.
- **LLM #1 (refinement)** only fixes recognition mistakes, technical terms, acronyms and punctuation. It doesn't summarize.
- **LLM #2 (analysis)** only reads the refined transcript. 

## Setup

You need Python 3.10+ (tested on 3.13), Node.js (for the frontend), a Groq API key, and a Hugging Face token.

### 1. Backend Installation

```powershell
# In the project root
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env`:
```env
GROQ_API_KEY=your_groq_api_key_here
HUGGINGFACE_TOKEN=your_huggingface_token_here
```

### 2. Frontend Installation

```powershell
cd speakex-frontend
npm install
# Create an environment file pointing to the backend
echo VITE_API_BASE_URL=http://127.0.0.1:8000 > .env
```

## Running the Application

**Start the Backend:**
```powershell
# From the project root with the virtual environment activated
uvicorn api:app --port 8000
```

**Start the Frontend:**
```powershell
# In a new terminal, inside the speakex-frontend folder
npm run dev
```

Then open `http://localhost:5173` (or the port Vite provides) in your browser.

*Note: The original Streamlit UI is still available as a fallback by running `python -m streamlit run app.py`.*

## Tests

```powershell
# From the project root
$env:PYTHONPATH="."
python -m pytest tests\
```
The test suite covers schema validation, ML chunking rules, exporters, API contracts, and security rules. E2E verification is also included for full pipeline integration. 

## Known Limitations

- Diarization on CPU is slow (roughly 1 to 1.5× the recording length). A GPU makes it much faster.
- Very long meetings may hit Groq's free-tier tokens-per-minute limits.
- Only English is supported.

## Security Considerations

- API Keys remain entirely backend-bound. The frontend never accesses or requests `GROQ_API_KEY` or `HUGGINGFACE_TOKEN`.
- Secrets are explicitly scrubbed from exceptions and error logs inside the pipeline execution.
- Downloads are dynamically mapped through backend proxy paths ensuring no sensitive data is bundled into Javascript clients.
