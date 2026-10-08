import uuid
import tempfile
import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse

from meeting_assistant.pipeline import MeetingPipeline
from meeting_assistant.schemas import MeetingRecord
from meeting_assistant.exporters import record_as_markdown

app = FastAPI(title="Meeting Assistant API")

frontend_origin = os.getenv("ALLOWED_ORIGIN", "http://localhost:8080")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS = {}
pipeline = MeetingPipeline()

def process_audio_job(job_id: str, temp_dir: str, audio_path: Path, filename: str):
    try:
        def update_status(message: str):
            stage = "processing"
            lower_msg = message.lower()
            if "decoding audio" in lower_msg:
                stage = "transcription"
            elif "diarization" in lower_msg:
                stage = "diarization"
            elif "refining" in lower_msg:
                stage = "refinement"
            elif "summary" in lower_msg or "minutes" in lower_msg:
                stage = "analysis"
            elif "packaging" in lower_msg:
                stage = "organization"
                
            JOBS[job_id]["stage"] = stage
            JOBS[job_id]["message"] = message

        JOBS[job_id]["status"] = "processing"
        
        record = pipeline.process(audio_path, source_filename=filename, on_status=update_status)
        
        JOBS[job_id]["status"] = "complete"
        JOBS[job_id]["stage"] = "complete"
        JOBS[job_id]["message"] = "Processing complete."
        JOBS[job_id]["result"] = record.model_dump(mode="json")
        
    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["stage"] = "error"
        JOBS[job_id]["message"] = str(e)

@app.post("/api/process")
async def process_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
        
    suffix = Path(file.filename).suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="File has no extension")
        
    job_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix="meeting-api-")
    audio_path = Path(temp_dir) / f"recording{suffix}"
    
    with open(audio_path, "wb") as f:
        f.write(await file.read())
        
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "stage": "upload",
        "message": "Queued for processing...",
        "temp_dir": temp_dir
    }
    
    background_tasks.add_task(process_audio_job, job_id, temp_dir, audio_path, file.filename)
    
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
def status_endpoint(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "stage": job["stage"],
        "message": job["message"]
    }

@app.get("/api/result/{job_id}")
def result_endpoint(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = JOBS[job_id]
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Job is not complete")
        
    return job["result"]

@app.get("/api/download/{job_id}/markdown")
def download_markdown(job_id: str):
    if job_id not in JOBS or JOBS[job_id]["status"] != "complete":
        raise HTTPException(status_code=404, detail="Job not found or not complete")
        
    record = MeetingRecord.model_validate(JOBS[job_id]["result"])
    md_content = record_as_markdown(record)
    return PlainTextResponse(
        content=md_content, 
        media_type="text/markdown", 
        headers={"Content-Disposition": "attachment; filename=meeting_record.md"}
    )

@app.get("/api/download/{job_id}/json")
def download_json(job_id: str):
    if job_id not in JOBS or JOBS[job_id]["status"] != "complete":
        raise HTTPException(status_code=404, detail="Job not found or not complete")
        
    return JSONResponse(
        content=JOBS[job_id]["result"], 
        headers={"Content-Disposition": "attachment; filename=meeting_record.json"}
    )
