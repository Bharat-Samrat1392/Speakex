import os
import zipfile

def create_archive(zip_name, source_dirs, exclude_dirs, exclude_files, exclude_exts):
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for source in source_dirs:
            if os.path.isfile(source):
                zipf.write(source, source)
                continue
                
            for root, dirs, files in os.walk(source):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
                
                for file in files:
                    if file in exclude_files or any(file.endswith(ext) for ext in exclude_exts):
                        continue
                    
                    filepath = os.path.join(root, file)
                    arcname = filepath # Keep relative path
                    zipf.write(filepath, arcname)

if __name__ == "__main__":
    sources = [
        "app.py", "api.py", "requirements.txt", "README.md", 
        "UI_AESTHETIC_CHANGELOG_DRAFT.md", ".env.example",
        "meeting_assistant", "prompts", "tests", "speakex-frontend",
        r"Final_Submission\clip_10.mp4" # Include demo recording
    ]
    
    excludes_dirs = {
        "node_modules", "__pycache__", ".pytest_cache", ".venv", 
        "dist", ".output", ".nitro", ".wrangler"
    }
    exclude_files = {".env", "Speakex_Final_Submission.zip"}
    exclude_exts = {".pyc", ".log", ".sqlite3"}
    
    create_archive("Speakex_Final_Submission.zip", sources, excludes_dirs, exclude_files, exclude_exts)
    print("Archive created successfully!")
