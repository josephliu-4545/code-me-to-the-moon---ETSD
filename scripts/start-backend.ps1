# Start the FastAPI backend on http://127.0.0.1:8000 (reloads on code changes).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
