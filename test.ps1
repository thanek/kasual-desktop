# Test runner for Windows. Mirrors test.sh — runs the core suite and each
# bundled app's tests. Uses the venv Python (kasual.ps1 uses the same).
#
# evdev-based tests are auto-skipped: conftest.py mocks evdev when it's not
# installed, and test_gamepad_watcher.py carries a platform skipif guard.
#
# Usage:
#   .\test.ps1              # run everything
#   .\test.ps1 -v           # verbose (passes args through to pytest)
#   .\test.ps1 tests/test_tile_bar.py -v   # specific file

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "venv Python not found at $Python" -ForegroundColor Red
    Write-Host "Create it with: python -m venv venv; .\venv\Scripts\pip install -r requirements.txt pytest pytest-qt" -ForegroundColor Yellow
    exit 1
}

$overall = 0

Write-Host "=== Kasual Desktop (core) ===" -ForegroundColor Cyan
& $Python -m pytest $PytestArgs
if ($LASTEXITCODE -ne 0) { $overall = 1 }

# Run each bundled app's tests (mirrors test.sh's loop over apps/*/)
Get-ChildItem -Path (Join-Path $ProjectRoot "apps") -Directory | ForEach-Object {
    $appDir = $_.FullName
    $appTests = Join-Path $appDir "tests"
    if (-not (Test-Path $appTests)) { return }

    $appName = $_.Name
    Write-Host ""
    Write-Host "=== $appName ===" -ForegroundColor Cyan
    & $Python -m pytest $appTests $PytestArgs
    if ($LASTEXITCODE -ne 0) { $overall = 1 }
}

if ($overall -eq 0) {
    Write-Host ""
    Write-Host "All tests passed." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Some tests failed." -ForegroundColor Red
}

exit $overall
