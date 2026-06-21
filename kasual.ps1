# Kasual Desktop Launcher for Windows (PowerShell)
# Clears Python cache before running - useful for development

$ErrorActionPreference = "SilentlyContinue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# --provisioning: re-trigger first-run onboarding by removing the marker, so the
# next launch shows the app picker again (mirrors kasual.sh). --provision is an alias.
if ($args[0] -eq '--provisioning' -or $args[0] -eq '--provision') {
    $marker = Join-Path $env:APPDATA 'kasual-desktop\.provisioned'
    if (Test-Path $marker) { Remove-Item $marker -Force }
    Write-Host "Removed provisioning marker - onboarding will run on next launch." -ForegroundColor Yellow
}

# Clear Python __pycache__ directories
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Filter "*.pyc" | Remove-Item -Force

# Also clear venv cache
Get-ChildItem -Path "$ProjectRoot\venv" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "Cache cleared. Starting Kasual Desktop..." -ForegroundColor Cyan

# Run Kasual Desktop
& "$ProjectRoot\venv\Scripts\python.exe" "$ProjectRoot\src\infrastructure\windows\windows_main.py"