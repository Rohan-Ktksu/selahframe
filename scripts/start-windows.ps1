$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path .\.venv\Scripts\python.exe)) { throw 'Run scripts/setup-windows.ps1 first.' }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { throw 'App failed to start. Run scripts/doctor-windows.ps1.' }
