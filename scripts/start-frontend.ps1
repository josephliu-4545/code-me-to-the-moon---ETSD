# Start the Vite dev server on http://127.0.0.1:5173 (proxies /api to the backend on port 8000).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
if (-not (Test-Path node_modules)) { npm ci }
npm run dev -- --host 127.0.0.1
