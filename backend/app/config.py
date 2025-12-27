"""Configuration constants for the application."""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime

# Load .env file if exists
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ===== Logging Configuration =====
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "text" or "json"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
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
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
    
    root_logger.addHandler(handler)


setup_logging()

# ===== OAuth Constants =====
# Client ID should be set via environment variable for security
# Default is the public Codex CLI client ID (safe to use as it's public)
OPENAI_CLIENT_ID = os.getenv("OPENAI_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann")
OPENAI_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
OPENAI_REDIRECT_URI = os.getenv("OPENAI_REDIRECT_URI", "http://localhost:1455/auth/callback")
OPENAI_SCOPE = "openid profile email offline_access"

# OAuth state expiration (seconds)
OAUTH_STATE_EXPIRATION = 600  # 10 minutes

# ===== API URLs =====
CODEX_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_MODEL_NAME = os.getenv("CODEX_MODEL_NAME", "gpt-5.1-codex")

# ===== Server Configuration =====
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "1455"))

# Allowed origins for CORS (Tauri app)
# In production, only Tauri origins are needed
_DEV_ORIGINS = ["http://localhost:1420"] if os.getenv("AICAP_DEV_MODE", "").lower() == "true" else []
CORS_ORIGINS = [
    "tauri://localhost",       # Tauri production
    "https://tauri.localhost", # Tauri production (alternative)
] + _DEV_ORIGINS

# ===== Rate Limiting =====
RATE_LIMIT_REQUESTS = 60  # requests per minute
RATE_LIMIT_WINDOW = 60    # seconds

# Auth endpoints have stricter limits
AUTH_RATE_LIMIT_REQUESTS = 5  # requests per minute
AUTH_RATE_LIMIT_WINDOW = 60   # seconds

# ===== Credential Storage =====
CREDENTIAL_SERVICE = "aicap"
CREDENTIAL_OPENAI = "openai-tokens"

# ===== Scheduler =====
UPDATE_INTERVAL_MINUTES = 5
