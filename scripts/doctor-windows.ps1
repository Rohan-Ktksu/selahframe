$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { Write-Host 'MISSING virtual environment. Run scripts/setup-windows.ps1.'; exit 1 }
& $python -c "import fastapi, uvicorn, requests, PIL, multipart, dotenv; from app.media import readiness; r=readiness(); [print(('READY ' if v else 'MISSING ') + k) for k,v in r.items()]; raise SystemExit(0 if all(r.values()) else 1)"
$coreResult = $LASTEXITCODE
foreach ($tool in @('ollama', 'rclone')) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) { Write-Host "OPTIONAL FOUND $tool" }
    else { Write-Host "OPTIONAL NOT INSTALLED $tool" }
}
if ($coreResult -ne 0) { Write-Host 'Run scripts/setup-media-windows.ps1. See docs/INSTALL_WINDOWS.md for troubleshooting.' }
Write-Host 'No credentials or project text are printed. Manual narration and local export do not require Ollama or Drive.'
exit $coreResult
