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

# -- Driver check: ViGEmBus + HidHide ----------------------------------------
# Exclusive gamepad mode (virtual pad + hidden physical device) requires both
# kernel drivers. If either is missing, Kasual falls back to cooperative mode
# (pad bleed to foreground apps will occur). Warn the user but still start.
$vigembus = Get-Service -Name 'ViGEmBus' -ErrorAction SilentlyContinue
$hidhide  = Get-Service -Name 'HidHide'  -ErrorAction SilentlyContinue
if (-not $vigembus -or -not $hidhide) {
    Write-Host ""
    Write-Host "+-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "|  Exclusive gamepad mode requires two kernel drivers:      |" -ForegroundColor Yellow
    if (-not $vigembus) {
        Write-Host "|    X ViGEmBus  (virtual Xbox360 controller)  NOT FOUND   |" -ForegroundColor Red
    } else {
        Write-Host "|    + ViGEmBus  (virtual Xbox360 controller)  installed   |" -ForegroundColor Green
    }
    if (-not $hidhide) {
        Write-Host "|    X HidHide   (HID device hiding)           NOT FOUND   |" -ForegroundColor Red
    } else {
        Write-Host "|    + HidHide   (HID device hiding)           installed   |" -ForegroundColor Green
    }
    Write-Host "|                                                           |" -ForegroundColor Yellow
    Write-Host "|  Without both drivers Kasual runs in cooperative mode:   |" -ForegroundColor Yellow
    Write-Host "|  foreground apps (Steam, games) will see the physical pad |" -ForegroundColor Yellow
    Write-Host "|  and may react to gamepad navigation simultaneously.     |" -ForegroundColor Yellow
    Write-Host "|                                                           |" -ForegroundColor Yellow
    Write-Host "|  Download from:                                           |" -ForegroundColor Yellow
    Write-Host "|    https://github.com/nefarius/ViGEmBus/releases          |" -ForegroundColor Cyan
    Write-Host "|    https://github.com/nefarius/HidHide/releases           |" -ForegroundColor Cyan
    Write-Host "+-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Starting in cooperative mode in 3 seconds..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 3
}

# Clear Python __pycache__ directories
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Filter "*.pyc" | Remove-Item -Force

# Also clear venv cache
Get-ChildItem -Path "$ProjectRoot\venv" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "Cache cleared. Starting Kasual Desktop..." -ForegroundColor Cyan

# Run Kasual Desktop
& "$ProjectRoot\venv\Scripts\python.exe" "$ProjectRoot\src\windows_main.py"