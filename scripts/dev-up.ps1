param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$stateDir = Join-Path $root ".dev"
$backendPidFile = Join-Path $stateDir "backend.pid"
$frontendPidFile = Join-Path $stateDir "frontend.pid"

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at $pythonExe"
}

$backendCommand = "Set-Location '$root'; & '$pythonExe' -m uvicorn backend.app.main:app --reload --port $BackendPort"
$frontendCommand = "Set-Location '$root\frontend'; npm run dev -- --port $FrontendPort"

$backendProcess = Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $backendCommand -PassThru
$frontendProcess = Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $frontendCommand -PassThru

Set-Content -Path $backendPidFile -Value $backendProcess.Id
Set-Content -Path $frontendPidFile -Value $frontendProcess.Id

Write-Host "Backend started on http://localhost:$BackendPort (PID=$($backendProcess.Id))"
Write-Host "Frontend started on http://localhost:$FrontendPort (PID=$($frontendProcess.Id))"
Write-Host "Use scripts/dev-down.ps1 to stop both processes."
