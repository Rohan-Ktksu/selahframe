param([switch]$SkipFFmpeg, [switch]$SkipVoice)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run scripts/setup-windows.ps1 first.' }
Write-Host 'Piper: GPL-3.0. Voice model repository: MIT; LJ Speech dataset: public domain.'
Write-Host 'See docs/THIRD_PARTY.md for sources and redistribution notices.'
& $python -m pip install -r requirements-media.txt
if ($LASTEXITCODE -ne 0) { throw 'Piper installation failed.' }
New-Item -ItemType Directory -Force tools\downloads,voices | Out-Null
if (!$SkipFFmpeg) {
    $existing = Get-ChildItem -Path tools\ffmpeg -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue
    if (!$existing) {
        $archive = Join-Path (Get-Location) 'tools\downloads\ffmpeg-essentials.zip'
        Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $archive
        $expected = (Invoke-RestMethod 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256').Trim().Split(' ')[0]
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'FFmpeg SHA-256 verification failed; archive will not be used.' }
        Expand-Archive -LiteralPath $archive -DestinationPath tools\ffmpeg
        Write-Host 'FFmpeg archive checksum verified and extracted on the project drive.'
    }
}
if (!$SkipVoice) {
    & $python -m piper.download_voices --data-dir voices en_US-ljspeech-medium
    if ($LASTEXITCODE -ne 0) { throw 'Voice download failed.' }
    Invoke-WebRequest 'https://huggingface.co/rhasspy/piper-voices/raw/main/en/en_US/ljspeech/medium/MODEL_CARD' -OutFile voices\en_US-ljspeech-medium.MODEL_CARD
}
Write-Host 'Default voice: en_US-ljspeech-medium. If .env has an older PIPER_MODEL, change it to this voice.'
& $python -m piper --help
if ($LASTEXITCODE -ne 0) { throw 'Piper CLI check failed.' }
& .\scripts\doctor-windows.ps1
