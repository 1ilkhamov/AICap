"""Configuration constants for the application."""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime, timezone

# Load .env file if exists
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ===== Application Version =====
VERSION = "1.2.0"

# ===== Logging Configuration =====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "text" or "json"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging():
    """Configure logging based on environment."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)


setup_logging()

# ===== OAuth Constants =====
# Client ID should be set via environment variable for security
# Default is the public Codex CLI client ID (safe to use as it's public)
OPENAI_CLIENT_ID = os.getenv("OPENAI_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann")
OPENAI_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_REDIRECT_URI = os.getenv(
    "OPENAI_REDIRECT_URI", "http://localhost:1455/auth/callback"
)
OPENAI_SCOPE = "openid profile email offline_access"

# OAuth state expiration (seconds)
OAUTH_STATE_EXPIRATION = 600  # 10 minutes

# ===== API URLs =====
CODEX_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_MODEL_NAME = os.getenv("CODEX_MODEL_NAME", "gpt-5.1-codex")

# ===== Server Configuration =====
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "1455"))
AICAP_API_TOKEN = os.getenv("AICAP_API_TOKEN")

# Allowed origins for CORS (Tauri app)

# In production, only Tauri origins are needed
_DEV_ORIGINS = (
    ["http://localhost:1420"]
    if os.getenv("AICAP_DEV_MODE", "").lower() == "true"
    else []
)
CORS_ORIGINS = [
    "tauri://localhost",  # Tauri production
    "https://tauri.localhost",  # Tauri production (alternative)
] + _DEV_ORIGINS

# ===== Rate Limiting =====
RATE_LIMIT_REQUESTS = 60  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds

# Auth endpoints have stricter limits
AUTH_RATE_LIMIT_REQUESTS = 5  # requests per minute
AUTH_RATE_LIMIT_WINDOW = 60  # seconds

# ===== Credential Storage =====
CREDENTIAL_SERVICE = "aicap"
CREDENTIAL_OPENAI = "openai-tokens"

# ===== Scheduler =====
UPDATE_INTERVAL_MINUTES = 5

# ===== Google Antigravity OAuth =====
# Client credentials must be set via environment variables
# Get your credentials from Google Cloud Console: https://console.cloud.google.com/apis/credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:1455/auth/callback"
)
GOOGLE_SCOPES = " ".join([
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "openid",
])

# Antigravity API
ANTIGRAVITY_API_URL = "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"


def is_google_oauth_configured() -> bool:
    """Check if Google OAuth credentials are configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# ===== Account ID Validation =====
ACCOUNT_ID_LENGTH = 8  # UUID prefix length used for account IDs
ACCOUNT_ID_PATTERN_STR = f"^[0-9a-f]{{{ACCOUNT_ID_LENGTH}}}$"


# ===== Startup Safety =====
def is_loopback_host(host: str) -> bool:
    """Check if host is a loopback address (safe for binding without token)."""
    if host in ("localhost", "::1"):
        return True
    if host.startswith("127."):
        return True
    return False


def validate_host_security(host: str, token: str | None) -> None:
    """Validate that non-loopback hosts require API token.

    Raises SystemExit if binding to non-loopback without AICAP_API_TOKEN.
    """
    if not is_loopback_host(host) and not token:
        import sys

        print(
            f"ERROR: Binding to non-loopback host '{host}' requires AICAP_API_TOKEN.\n"
            "Set AICAP_API_TOKEN environment variable or use a loopback address (127.0.0.1, localhost).",
            file=sys.stderr,
        )
        sys.exit(1)
