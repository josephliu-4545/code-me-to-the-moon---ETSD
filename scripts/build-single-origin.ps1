# Build the frontend for serving by the backend at /app/ (one process, one origin).
# Then start the backend with FRONTEND_DIST_DIR pointing at frontend\dist and open http://127.0.0.1:8000/app/
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
$env:VITE_BASE = "/app/"
npm run build
Write-Host "Built. Set FRONTEND_DIST_DIR=$((Resolve-Path dist).Path) in backend\.env and start the backend."
