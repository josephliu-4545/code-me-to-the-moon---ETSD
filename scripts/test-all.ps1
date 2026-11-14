# Run every ordinary (non-live) check: backend tests, then frontend typecheck, lint, tests and build.
$ErrorActionPreference = "Stop"
$root = Join-Path $PSScriptRoot ".."
Push-Location (Join-Path $root "backend")
try { .\.venv\Scripts\python.exe -m pytest -m "not integration" -q; if ($LASTEXITCODE) { throw "backend tests failed" } } finally { Pop-Location }
Push-Location (Join-Path $root "frontend")
try {
  npm run typecheck; if ($LASTEXITCODE) { throw "typecheck failed" }
  npm run lint; if ($LASTEXITCODE) { throw "lint failed" }
  npm test; if ($LASTEXITCODE) { throw "frontend tests failed" }
  npm run build; if ($LASTEXITCODE) { throw "build failed" }
} finally { Pop-Location }
Write-Host "All checks passed."
