$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$stateDir = Join-Path $root ".dev"
$pidFiles = @(
    Join-Path $stateDir "backend.pid",
    Join-Path $stateDir "frontend.pid"
)

foreach ($pidFile in $pidFiles) {
    if (-not (Test-Path $pidFile)) {
        continue
    }

    $pidText = (Get-Content -Path $pidFile -Raw).Trim()
    if ($pidText -match '^[0-9]+$') {
        $pid = [int]$pidText
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Stop-Process -Id $pid -Force
            Write-Host "Stopped process PID=$pid"
        }
    }

    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Local dev processes stopped (if running)."
