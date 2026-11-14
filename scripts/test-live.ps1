# Opt-in live checks against NASA POWER and Google Earth Engine (needs network and EE credentials).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
$env:RUN_POWER_INTEGRATION = "1"
$env:RUN_EE_INTEGRATION = "1"
if (-not $env:EE_PROJECT_ID) {
  $line = Get-Content .env | Where-Object { $_ -match '^EE_PROJECT_ID=' } | Select-Object -First 1
  if ($line) { $env:EE_PROJECT_ID = ($line -split '=', 2)[1].Trim().Trim('"') }
}
.\.venv\Scripts\python.exe -m pytest tests/integration -q
