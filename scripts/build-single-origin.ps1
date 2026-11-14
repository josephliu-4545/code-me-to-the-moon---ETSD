# Build the frontend, serve it with the backend at /app/ (one process, one origin), and open the app.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location (Join-Path $root "frontend")
try {
  $env:VITE_BASE = "/app/"
  npm run build
  if ($LASTEXITCODE) { throw "frontend build failed" }
} finally { Pop-Location }

$env:FRONTEND_DIST_DIR = (Resolve-Path (Join-Path $root "frontend\dist")).Path
Write-Host "Serving $($env:FRONTEND_DIST_DIR) at http://127.0.0.1:8000/app/"

Start-Job -ScriptBlock {
  for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
      Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
      Start-Process "http://127.0.0.1:8000/app/"
      break
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
} | Out-Null

Push-Location (Join-Path $root "backend")
try {
  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
} finally { Pop-Location }
