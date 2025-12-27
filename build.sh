#!/bin/bash
# AICap Build Script for Linux/macOS

set -e

echo "=== AICap Build Script ==="

# Check prerequisites
echo -e "\nChecking prerequisites..."

# Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.11+"
    exit 1
fi
echo "  Python: OK"

# Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found. Please install Node.js 20+"
    exit 1
fi
echo "  Node.js: OK"

# Rust
if ! command -v cargo &> /dev/null; then
    echo "ERROR: Rust not found. Please install Rust from https://rustup.rs"
    exit 1
fi
echo "  Rust: OK"

# Step 1: Build Backend
echo -e "\n[1/3] Building backend..."
cd backend

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv and install deps
echo "  Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt -q

# Build with PyInstaller
echo "  Building executable..."
python build.py

deactivate
cd ..
echo "  Backend build complete!"

# Step 2: Install frontend dependencies
echo -e "\n[2/3] Installing frontend dependencies..."
cd desktop
npm install
cd ..
echo "  Frontend dependencies installed!"

# Step 3: Build Tauri app
echo -e "\n[3/3] Building Tauri application..."
cd desktop
npm run tauri build
cd ..
echo "  Tauri build complete!"

# Done
echo -e "\n=== Build Complete ==="
echo "Installer location: desktop/src-tauri/target/release/bundle/"
