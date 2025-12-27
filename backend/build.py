"""Build script for creating standalone backend executable."""

import PyInstaller.__main__
import platform
import shutil
from pathlib import Path

def build():
    """Build the backend as a standalone executable."""
    
    # Determine output name based on platform
    system = platform.system().lower()
    if system == "windows":
        output_name = "aicap-backend-x86_64-pc-windows-msvc"
    elif system == "darwin":
        arch = platform.machine()
        if arch == "arm64":
            output_name = "aicap-backend-aarch64-apple-darwin"
        else:
            output_name = "aicap-backend-x86_64-apple-darwin"
    else:
        output_name = "aicap-backend-x86_64-unknown-linux-gnu"
    
    # PyInstaller arguments
    args = [
        "run_server.py",
        "--onefile",
        "--name", output_name,
        "--clean",
        "--noconfirm",
        # Hidden imports for FastAPI
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.lifespan.off",
        "--hidden-import", "httpx",
        "--hidden-import", "apscheduler",
        "--hidden-import", "apscheduler.schedulers.asyncio",
        "--hidden-import", "cryptography",
        # Exclude unnecessary modules to reduce size
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",
    ]
    
    # Add console flag for Windows (hide console window)
    if system == "windows":
        args.append("--noconsole")
    
    print(f"Building {output_name}...")
    PyInstaller.__main__.run(args)
    
    # Copy to Tauri binaries folder
    dist_path = Path("dist") / (output_name + (".exe" if system == "windows" else ""))
    tauri_bin = Path("../desktop/src-tauri/binaries")
    tauri_bin.mkdir(parents=True, exist_ok=True)
    
    target_path = tauri_bin / dist_path.name
    if dist_path.exists():
        shutil.copy2(dist_path, target_path)
        print(f"Copied to {target_path}")
    else:
        print(f"ERROR: {dist_path} not found!")
        return False
    
    print("Build complete!")
    return True

if __name__ == "__main__":
    build()
