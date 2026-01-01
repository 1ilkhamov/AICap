"""Configuration constants for the application."""

import os
import sys
import logging
import json
import re
import tempfile
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

# API Token: support both direct env var and file-based secret (sidecar pattern)
# AICAP_API_TOKEN_FILE takes precedence if set
_api_token_from_file: str | None = None
_api_token_file_path = os.getenv("AICAP_API_TOKEN_FILE")
if _api_token_file_path:
    try:
        token_path = Path(_api_token_file_path)

        # Security: validate token file path before reading
        # 1. Must not be a symlink (check BEFORE resolve)
        if token_path.exists() and token_path.is_symlink():
            logging.getLogger(__name__).error(
                f"Security: token file cannot be a symlink: {_api_token_file_path}"
            )
        else:
            # 2. Must be within OS temp directory (robust Windows-safe check)
            temp_dir = Path(tempfile.gettempdir())
            try:
                # Normalize paths for comparison (Windows-safe: handles case, drive letters, separators)
                temp_dir_abs = os.path.normcase(os.path.abspath(temp_dir))
                token_path_abs = os.path.normcase(os.path.abspath(token_path))

                # Use commonpath to check containment
                common = os.path.commonpath([temp_dir_abs, token_path_abs])
                if os.path.normcase(common) != temp_dir_abs:
                    logging.getLogger(__name__).error(
                        f"Security: token file must be in temp directory. Got: {_api_token_file_path}"
                    )
                    resolved_path = None
                else:
                    resolved_path = token_path.resolve()

                    # Second containment check: ensure resolved path is still within temp directory
                    # Compare against resolved temp directory to handle symlinks properly
                    temp_dir_resolved = os.path.normcase(
                        os.path.abspath(Path(tempfile.gettempdir()).resolve())
                    )
                    resolved_path_abs = os.path.normcase(os.path.abspath(resolved_path))
                    common_resolved = os.path.commonpath(
                        [temp_dir_resolved, resolved_path_abs]
                    )
                    if os.path.normcase(common_resolved) != temp_dir_resolved:
                        logging.getLogger(__name__).error(
                            f"Security: resolved token file path escapes temp directory. Got: {resolved_path}"
                        )
                        resolved_path = None
            except (OSError, RuntimeError, ValueError) as e:
                logging.getLogger(__name__).error(
                    f"Cannot resolve token file path {_api_token_file_path}: {e}"
                )
                resolved_path = None

            # 3. Must match expected filename pattern: aicap-token-<hex>.txt (case-insensitive hex)
            if resolved_path and not re.match(
                r"^aicap-token-[0-9a-fA-F]+\.txt$", resolved_path.name
            ):
                logging.getLogger(__name__).error(
                    f"Security: token file must match pattern aicap-token-<hex>.txt. Got: {resolved_path.name}"
                )
            # 4. Must be a regular file (not special file)
            elif resolved_path and resolved_path.exists():
                if not resolved_path.is_file():
                    logging.getLogger(__name__).error(
                        f"Security: token file must be a regular file: {_api_token_file_path}"
                    )
                else:
                    # All validations passed - safe to read and delete
                    _api_token_from_file = resolved_path.read_text().strip()
                    # Best-effort deletion of token file after reading
                    try:
                        resolved_path.unlink()
                        logging.getLogger(__name__).info(
                            f"Read and deleted API token file: {_api_token_file_path}"
                        )
                    except OSError as e:
                        logging.getLogger(__name__).warning(
                            f"Could not delete API token file {_api_token_file_path}: {e}"
                        )
            elif resolved_path:
                logging.getLogger(__name__).warning(
                    f"AICAP_API_TOKEN_FILE set but file not found: {_api_token_file_path}"
                )
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Error reading API token file {_api_token_file_path}: {e}"
        )

AICAP_API_TOKEN = _api_token_from_file or os.getenv("AICAP_API_TOKEN")

# Dev mode flag for CORS and security warnings
AICAP_DEV_MODE = os.getenv("AICAP_DEV_MODE", "").lower() == "true"

# Allowed origins for CORS (Tauri app)

# In production, only Tauri origins are needed
_DEV_ORIGINS = ["http://localhost:1420"] if AICAP_DEV_MODE else []
CORS_ORIGINS = [
    "tauri://localhost",  # Tauri production
    "https://tauri.localhost",  # Tauri production (alternative)
] + _DEV_ORIGINS

# ===== Rate Limiting =====
RATE_LIMIT_REQUESTS = 60  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds

# Auth endpoints have stricter limits
AUTH_RATE_LIMIT_REQUESTS = 15  # requests per window
AUTH_RATE_LIMIT_WINDOW = 60  # seconds

# ===== Credential Storage =====
CREDENTIAL_SERVICE = "aicap"
CREDENTIAL_OPENAI = "openai-tokens"

# ===== Scheduler =====
UPDATE_INTERVAL_MINUTES = 5

# ===== Google Antigravity OAuth =====
# Public client credentials for Antigravity (desktop app - not secret)
# These are the same credentials used by Antigravity IDE
GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
)
GOOGLE_CLIENT_SECRET = os.getenv(
    "GOOGLE_CLIENT_SECRET",
    "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"
)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:1455/auth/callback"
)
GOOGLE_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
        "openid",
    ]
)

# Antigravity API
ANTIGRAVITY_API_URL = (
    "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
)


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
    Logs warning if dev mode enabled with non-loopback host.
    """
    logger = logging.getLogger(__name__)

    # Warn if dev mode is enabled with non-loopback host (potential security issue)
    if AICAP_DEV_MODE and not is_loopback_host(host):
        logger.warning(
            f"SECURITY WARNING: AICAP_DEV_MODE=true with non-loopback host '{host}'. "
            "Dev CORS origins are enabled. This should only be used in development environments."
        )

    if not is_loopback_host(host) and not token:
        import sys

        print(
            f"ERROR: Binding to non-loopback host '{host}' requires AICAP_API_TOKEN.\n"
            "Set AICAP_API_TOKEN environment variable or use a loopback address (127.0.0.1, localhost).",
            file=sys.stderr,
        )
        sys.exit(1)
