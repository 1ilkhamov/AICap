"""Entry point for standalone backend server."""

import sys
import os

# Ensure the app module can be found
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    app_dir = os.path.dirname(sys.executable)
else:
    # Running as script
    app_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, app_dir)

def main():
    """Start the backend server."""
    import uvicorn
    from app.main import app
    
    # Run on localhost only for security
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=1455,
        log_level="info",
        access_log=False,  # Reduce noise
    )

if __name__ == "__main__":
    main()
