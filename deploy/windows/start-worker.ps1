$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location (Join-Path $projectRoot 'backend')
try {
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') -m app.worker
    if ($LASTEXITCODE -ne 0) { throw 'Worker exited with an error.' }
} finally { Pop-Location }
