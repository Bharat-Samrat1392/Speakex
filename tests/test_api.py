import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_status_not_found():
    response = client.get("/api/status/invalid-id")
    assert response.status_code == 404

def test_result_not_found():
    response = client.get("/api/result/invalid-id")
    assert response.status_code == 404

# Since processing is extremely slow (involves Whisper and Groq), we won't mock it entirely in e2e tests
# but we can test the upload endpoint rejection of invalid files.

def test_process_no_file():
    # Sending empty post
    response = client.post("/api/process")
    assert response.status_code == 422 # FastAPI validation error for missing field

def test_process_no_extension():
    # Provide a file with no extension
    response = client.post(
        "/api/process",
        files={"file": ("noextension", b"fake audio data", "audio/wav")}
    )
    assert response.status_code == 400
    assert "no extension" in response.json()["detail"]
