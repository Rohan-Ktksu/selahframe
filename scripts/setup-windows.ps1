$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path .venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 from python.org, then rerun setup.' }
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
New-Item -ItemType Directory -Force -Path voices,data,output | Out-Null
if (!(Test-Path .env)) { Copy-Item .env.example .env }
Write-Host 'Next: scripts/setup-media-windows.ps1, then scripts/start-windows.ps1.'
