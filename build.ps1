# AICap Build Script for Windows
# This script builds the complete application

$ErrorActionPreference = "Stop"

Write-Host "=== AICap Build Script ===" -ForegroundColor Cyan

# Check prerequisites
Write-Host "`nChecking prerequisites..." -ForegroundColor Yellow

# Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
Write-Host "  Python: OK" -ForegroundColor Green

# Node.js
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "ERROR: Node.js not found. Please install Node.js 20+" -ForegroundColor Red
    exit 1
}
Write-Host "  Node.js: OK" -ForegroundColor Green

# Rust
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $cargo) {
    Write-Host "ERROR: Rust not found. Please install Rust from https://rustup.rs" -ForegroundColor Red
    exit 1
}
Write-Host "  Rust: OK" -ForegroundColor Green

# Step 1: Build Backend
Write-Host "`n[1/3] Building backend..." -ForegroundColor Yellow
Push-Location backend

# Create venv if not exists
if (-not (Test-Path "venv")) {
    Write-Host "  Creating virtual environment..."
    python -m venv venv
}

# Activate venv and install deps
Write-Host "  Installing dependencies..."
& .\venv\Scripts\pip.exe install -r requirements.txt -q

# Build with PyInstaller
Write-Host "  Building executable..."
& .\venv\Scripts\python.exe build.py

Pop-Location
Write-Host "  Backend build complete!" -ForegroundColor Green

# Step 2: Install frontend dependencies
Write-Host "`n[2/3] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location desktop
npm install
Pop-Location
Write-Host "  Frontend dependencies installed!" -ForegroundColor Green

# Step 3: Build Tauri app
Write-Host "`n[3/3] Building Tauri application..." -ForegroundColor Yellow
Push-Location desktop
npm run tauri build
Pop-Location
Write-Host "  Tauri build complete!" -ForegroundColor Green

# Done
Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
Write-Host "Installer location: desktop\src-tauri\target\release\bundle\" -ForegroundColor White
