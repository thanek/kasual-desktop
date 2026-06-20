# Kasual Desktop Launcher for Windows (PowerShell)
# Clears Python cache before running - useful for development

$ErrorActionPreference = "SilentlyContinue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Clear Python __pycache__ directories
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path "$ProjectRoot\src" -Recurse -Filter "*.pyc" | Remove-Item -Force

# Also clear venv cache
Get-ChildItem -Path "$ProjectRoot\venv" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "Cache cleared. Starting Kasual Desktop..." -ForegroundColor Cyan

# Run Kasual Desktop
& "$ProjectRoot\venv\Scripts\python.exe" "$ProjectRoot\src\infrastructure\windows\windows_main.py"