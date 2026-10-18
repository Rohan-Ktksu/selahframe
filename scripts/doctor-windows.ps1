$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$missing = 0
foreach ($tool in @('ffmpeg', 'ffprobe', 'ollama', 'rclone')) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) { Write-Host "FOUND $tool" }
    else { Write-Host "MISSING $tool"; $missing++ }
}
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $python) {
    & $python -c "import fastapi, uvicorn, PIL, requests, multipart, dotenv; print('PASS application imports')"
    if ($LASTEXITCODE -ne 0) { $missing++ }
    & $python -c "import importlib.util; print('Piper installed:', importlib.util.find_spec('piper') is not None)"
} else { Write-Host 'MISSING virtual environment; run scripts/setup-windows.ps1'; $missing++ }
if (!(Test-Path 'voices\en_US-lessac-medium.onnx')) { Write-Host 'MISSING default voice model; see docs/INSTALL_WINDOWS.md'; $missing++ }
Write-Host 'Install links: https://www.python.org/downloads/windows/ https://ffmpeg.org/download.html https://ollama.com/download/windows https://rclone.org/downloads/'
Write-Host 'Ollama and Drive are optional for manual-script/local-export use. No credentials are printed.'
if ($missing -gt 0) { exit 1 }
