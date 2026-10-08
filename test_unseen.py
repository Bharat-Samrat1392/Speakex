import requests
import time
import sys
import json

base_url = "http://127.0.0.1:8000/api"
file_path = r"D:\Bharat IITG\interiit\mlaeps\rough\monodi_test_clip.mp3"

print(f"Uploading {file_path}...")
with open(file_path, 'rb') as f:
    resp = requests.post(f"{base_url}/process", files={"file": f})
    
if not resp.ok:
    print(f"Upload failed: {resp.text}")
    sys.exit(1)
    
job_id = resp.json()["job_id"]
print(f"Job started: {job_id}")

while True:
    status_resp = requests.get(f"{base_url}/status/{job_id}")
    if not status_resp.ok:
        print(f"Status failed: {status_resp.text}")
        sys.exit(1)
    
    status = status_resp.json()
    print(f"Stage: {status['stage']} - {status.get('message', '')}")
    
    if status['stage'] == 'complete':
        break
    elif status['stage'] == 'error':
        print(f"Processing failed: {status}")
        sys.exit(1)
        
    time.sleep(2)
    
print("Fetching result...")
result_resp = requests.get(f"{base_url}/result/{job_id}")
result = result_resp.json()

print("\n--- Summary ---")
print(result['analysis']['summary'])
print("\n--- Decisions ---")
for d in result['analysis']['decisions']:
    print(f"- {d}")

print("\nTest completed successfully!")
