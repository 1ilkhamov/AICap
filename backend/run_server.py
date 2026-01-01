"""Entry point for standalone backend server."""

import sys
import os

# Ensure the app module can be found
if getattr(sys, "frozen", False):
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
    from app.config import API_HOST, API_PORT, AICAP_API_TOKEN, validate_host_security

    # Validate host security before starting
    validate_host_security(API_HOST, AICAP_API_TOKEN)

    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        access_log=False,  # Reduce noise
    )


if __name__ == "__main__":
    main()
