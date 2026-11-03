param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install backend/requirements.lock.txt first.' }
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port $Port --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'API exited with an error.' }
} finally { Pop-Location }
