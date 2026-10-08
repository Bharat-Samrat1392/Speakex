import time
import requests
from pathlib import Path
import json

API_URL = "http://127.0.0.1:8000/api"
FILE_PATH = "Final_Submission/clip_10.mp4"

def main():
    print(f"Uploading {FILE_PATH}...")
    with open(FILE_PATH, "rb") as f:
        resp = requests.post(f"{API_URL}/process", files={"file": ("clip_10.mp4", f, "video/mp4")})
        
    if resp.status_code != 200:
        print("Upload failed:", resp.text)
        return
        
    data = resp.json()
    job_id = data["job_id"]
    print(f"Job started: {job_id}")
    
    last_message = ""
    while True:
        status_resp = requests.get(f"{API_URL}/status/{job_id}")
        if status_resp.status_code != 200:
            print("Status fetch failed:", status_resp.text)
            break
            
        status_data = status_resp.json()
        status = status_data["status"]
        message = status_data["message"]
        
        if message != last_message:
            print(f"[{status_data['stage']}] {message}")
            last_message = message
            
        if status == "complete":
            print("\nProcessing complete! Fetching results...")
            break
        elif status == "error":
            print("Processing failed!")
            break
            
        time.sleep(1)

    if status == "complete":
        result_resp = requests.get(f"{API_URL}/result/{job_id}")
        result = result_resp.json()
        print("\nSpeakers:", result.get("speakers"))
        print("\nRaw Transcript snippet:\n", result.get("raw_transcript")[:200], "...")
        print("\nSummary:\n", result.get("analysis", {}).get("summary"))
        print("\nDecisions:", result.get("analysis", {}).get("decisions"))
        print("\nAction Items:", result.get("analysis", {}).get("action_items"))
        
        # Test downloads
        md_resp = requests.get(f"{API_URL}/download/{job_id}/markdown")
        if md_resp.status_code == 200:
            print(f"\nMarkdown download successful, length: {len(md_resp.text)}")
        else:
            print("\nMarkdown download failed:", md_resp.text)
            
if __name__ == "__main__":
    main()
