"""FastAPI application for AICap."""

import asyncio
import hmac
import logging
import time
import uuid
import webbrowser
import threading
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime


from fastapi import FastAPI, HTTPException, Query, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from .providers.openai_codex import OpenAICodexProvider, UsageLimits
from .providers.antigravity import AntigravityProvider
from .auth.credentials import CredentialManager
from .auth.state_manager import oauth_state_manager
from .config import (
    VERSION,
    UPDATE_INTERVAL_MINUTES,
    CORS_ORIGINS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    AUTH_RATE_LIMIT_REQUESTS,
    AUTH_RATE_LIMIT_WINDOW,
    AICAP_API_TOKEN,
    API_HOST,
    API_PORT,
    ACCOUNT_ID_LENGTH,
    validate_host_security,
)


logger = logging.getLogger(__name__)

API_TOKEN_HEADER = "X-AICap-Token"
REQUEST_ID_HEADER = "X-Request-ID"

# Account ID validation pattern (8 lowercase hex characters)
ACCOUNT_ID_PATTERN = re.compile(f"^[0-9a-f]{{{ACCOUNT_ID_LENGTH}}}$")


def validate_account_id(account_id: str) -> bool:
    """Validate account_id format: exactly 8 lowercase hex characters."""
    return bool(ACCOUNT_ID_PATTERN.match(account_id))


# Global State

providers = {
    "openai": OpenAICodexProvider(),
    "antigravity": AntigravityProvider(),
}
cached_limits: dict[str, UsageLimits] = {}
_cached_limits_lock = threading.Lock()  # Protects cached_limits dict access
last_update: Optional[datetime] = None
scheduler = AsyncIOScheduler()
_update_limits_lock = asyncio.Lock()
_update_limits_task: Optional[asyncio.Task] = None

# Thread-safe rate limiting

_rate_limit_lock = threading.Lock()
_auth_rate_limit_lock = threading.Lock()
rate_limit_storage: dict[str, list[float]] = defaultdict(list)
auth_rate_limit_storage: dict[str, list[float]] = defaultdict(list)
rate_limit_last_seen: dict[str, float] = {}
auth_rate_limit_last_seen: dict[str, float] = {}
app_start_time: float = time.time()


def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit (thread-safe)."""
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW

    with _rate_limit_lock:
        rate_limit_storage[client_ip] = [
            ts for ts in rate_limit_storage[client_ip] if ts > window_start
        ]
        if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_REQUESTS:
            rate_limit_last_seen[client_ip] = now
            return False
        rate_limit_storage[client_ip].append(now)
        rate_limit_last_seen[client_ip] = now
        return True


def check_auth_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded auth rate limit (thread-safe, stricter)."""
    now = time.time()
    window_start = now - AUTH_RATE_LIMIT_WINDOW

    with _auth_rate_limit_lock:
        auth_rate_limit_storage[client_ip] = [
            ts for ts in auth_rate_limit_storage[client_ip] if ts > window_start
        ]
        if len(auth_rate_limit_storage[client_ip]) >= AUTH_RATE_LIMIT_REQUESTS:
            auth_rate_limit_last_seen[client_ip] = now
            return False
        auth_rate_limit_storage[client_ip].append(now)
        auth_rate_limit_last_seen[client_ip] = now
        return True


def cleanup_rate_limit_storage() -> None:
    """Periodic cleanup of rate limit storage to prevent memory leaks."""
    now = time.time()
    expired_general = 0
    expired_auth = 0

    with _rate_limit_lock:
        expired_ips_general = {
            ip
            for ip, last_seen in rate_limit_last_seen.items()
            if last_seen < now - RATE_LIMIT_WINDOW * 2
        }
        orphaned_ips_general = {
            ip for ip, timestamps in rate_limit_storage.items() if not timestamps
        }
        for ip in expired_ips_general | orphaned_ips_general:
            rate_limit_storage.pop(ip, None)
            rate_limit_last_seen.pop(ip, None)
        expired_general = len(expired_ips_general | orphaned_ips_general)

    with _auth_rate_limit_lock:
        expired_ips_auth = {
            ip
            for ip, last_seen in auth_rate_limit_last_seen.items()
            if last_seen < now - AUTH_RATE_LIMIT_WINDOW * 2
        }
        orphaned_ips_auth = {
            ip for ip, timestamps in auth_rate_limit_storage.items() if not timestamps
        }
        for ip in expired_ips_auth | orphaned_ips_auth:
            auth_rate_limit_storage.pop(ip, None)
            auth_rate_limit_last_seen.pop(ip, None)
        expired_auth = len(expired_ips_auth | orphaned_ips_auth)

    if expired_general or expired_auth:
        logger.debug(
            "Cleaned up rate limit entries: "
            f"{expired_general} general, {expired_auth} auth"
        )


async def _run_update_all_limits() -> None:
    """Perform a single limits refresh for all providers.

    Uses atomic update pattern: collects all results first, then updates
    the shared dict in one operation under lock to prevent race conditions.
    """
    global cached_limits, last_update

    # Collect new limits without holding any lock (network calls happen here)
    new_limits: dict[str, UsageLimits] = {}
    for name, provider in providers.items():
        if provider.is_authenticated():
            try:
                new_limits[name] = await provider.get_limits()
            except Exception as e:
                logger.error("Failed to update limits for %s: %s", name, e)

    # Atomic update: merge new limits into cached_limits under lock
    with _cached_limits_lock:
        for name, limits in new_limits.items():
            cached_limits[name] = limits

    last_update = datetime.now()
    logger.info("Updated limits for %s providers", len(new_limits))


async def update_all_limits():
    """Update limits for all authenticated providers."""
    global _update_limits_task
    async with _update_limits_lock:
        if _update_limits_task is None or _update_limits_task.done():
            _update_limits_task = asyncio.create_task(_run_update_all_limits())
        task = _update_limits_task
    try:
        await asyncio.shield(task)
    finally:
        if task.done():
            async with _update_limits_lock:
                if _update_limits_task is task:
                    _update_limits_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    scheduler.add_job(
        update_all_limits,
        "interval",
        minutes=UPDATE_INTERVAL_MINUTES,
        id="update_limits",
    )
    scheduler.add_job(
        cleanup_rate_limit_storage, "interval", minutes=10, id="cleanup_rate_limits"
    )
    scheduler.add_job(
        oauth_state_manager.cleanup_expired,
        "interval",
        minutes=5,
        id="cleanup_oauth_states",
    )
    scheduler.start()
    logger.info("Scheduler started with cleanup jobs")
    await update_all_limits()
    yield
    scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")


app = FastAPI(
    title="AICap",
    description="Track API usage limits for AI services like OpenAI Codex",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "status", "description": "Service status and health"},
        {"name": "limits", "description": "Usage limits operations"},
        {"name": "auth", "description": "Authentication operations"},
        {"name": "accounts", "description": "Multi-account management"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", API_TOKEN_HEADER],
)


def _is_exempt_path(path: str) -> bool:
    """Check if path is exempt from authentication (health checks and OAuth callbacks).

    Handles trailing slashes consistently: /health and /health/ are both exempt.
    """
    # Normalize: strip trailing slash for comparison (but "/" stays as "/")
    normalized = path.rstrip("/") or "/"
    return normalized in {"/health", "/auth/callback"}


def _requires_api_token(path: str) -> bool:
    """Determine if a path requires API token authentication.

    When AICAP_API_TOKEN is set, these paths are protected:
    - All /api/* endpoints
    - Documentation endpoints (/docs, /redoc, /openapi.json)
    - Status/metrics endpoints (/status, /metrics, /limits/*)
    - Auth endpoints (except /auth/callback which handles OAuth redirects)
    """
    # Always allow these without token (health checks and OAuth callbacks)
    if _is_exempt_path(path):
        return False

    # Protect documentation endpoints when token is configured
    # Use prefix matching to cover /docs, /docs/, /docs/oauth2-redirect, /redoc, /redoc/, etc.
    if path == "/openapi.json":
        return True
    if path == "/docs" or path.startswith("/docs/"):
        return True
    if path == "/redoc" or path.startswith("/redoc/"):
        return True

    # Protect all API routes
    if path == "/api" or path.startswith("/api/"):
        return True

    # Protect legacy/status routes
    if path in {"/status", "/metrics", "/limits"} or path.startswith("/limits/"):
        return True

    # Protect auth routes (except callback handled above)
    if path.startswith("/auth/"):
        return True

    return False


@app.middleware("http")
async def api_token_middleware(request: Request, call_next):
    # Allow CORS preflight requests to pass through
    if request.method == "OPTIONS":
        return await call_next(request)
    if not AICAP_API_TOKEN:
        return await call_next(request)
    path = request.url.path
    if not _requires_api_token(path):
        return await call_next(request)
    provided_token = request.headers.get(API_TOKEN_HEADER)

    if not provided_token or not hmac.compare_digest(provided_token, AICAP_API_TOKEN):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Allow CORS preflight requests to pass through
    if request.method == "OPTIONS":
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    return await call_next(request)


def _is_loopback_client(client_ip: str) -> bool:
    """Check if the client IP is a loopback address.

    Allows 'testclient' for FastAPI TestClient compatibility.
    Fails closed: unknown/missing clients are NOT treated as loopback.
    """
    if client_ip in ("localhost", "::1", "testclient"):
        return True
    if client_ip.startswith("127."):
        return True
    return False


@app.middleware("http")
async def loopback_only_middleware(request: Request, call_next):
    """Restrict non-loopback clients when AICAP_API_TOKEN is unset.

    When no API token is configured, only loopback clients (127.x.x.x, ::1, localhost)
    can access protected endpoints. This provides defense-in-depth even if the server
    is accidentally bound to 0.0.0.0 without a token.

    Exempt paths: /health (for external health checks) and /auth/callback (OAuth flow).
    """
    # Allow CORS preflight requests to pass through
    if request.method == "OPTIONS":
        return await call_next(request)
    if AICAP_API_TOKEN:
        # Token is set - token middleware handles auth
        return await call_next(request)

    path = request.url.path
    # Always allow health check and OAuth callback from any client
    if _is_exempt_path(path):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _is_loopback_client(client_ip):
        logger.warning(
            f"Rejected non-loopback client {client_ip} - AICAP_API_TOKEN not set"
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Access denied: loopback clients only when token not set"
            },
        )
    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add request ID for tracing and debugging."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


class StatusResponse(BaseModel):
    status: str
    providers: dict[str, bool]
    last_update: Optional[str]


# ===== API v1 Router =====
api_v1 = APIRouter(prefix="/api/v1")


@api_v1.get("/status", response_model=StatusResponse, tags=["status"])
async def get_status():
    """Get current service status and provider authentication states."""
    return StatusResponse(
        status="ok",
        providers={name: p.is_authenticated() for name, p in providers.items()},
        last_update=last_update.isoformat() if last_update else None,
    )


@api_v1.get("/limits", tags=["limits"])
async def get_all_limits() -> dict:
    """Get usage limits for all authenticated providers."""
    with _cached_limits_lock:
        providers_data = {
            name: limits.to_dict() for name, limits in cached_limits.items()
        }
    return {
        "last_update": last_update.isoformat() if last_update else None,
        "providers": providers_data,
    }


@api_v1.get("/limits/{provider}", tags=["limits"])
async def get_provider_limits(provider: str):
    """Get usage limits for a specific provider."""
    if provider not in providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    with _cached_limits_lock:
        if provider in cached_limits:
            return cached_limits[provider].to_dict()
    limits = await providers[provider].get_limits()
    with _cached_limits_lock:
        cached_limits[provider] = limits
    return limits.to_dict()


@api_v1.post("/limits/refresh", tags=["limits"])
async def refresh_limits() -> dict:
    """Force refresh limits for all authenticated providers."""
    await update_all_limits()
    return {
        "status": "ok",
        "last_update": last_update.isoformat() if last_update else None,
    }


@api_v1.get("/auth/{provider}/login", tags=["auth"])
async def login(
    request: Request,
    provider: str,
    open_browser: bool = Query(default=True),
    add_account: bool = Query(default=False),
):
    """Start OAuth authentication flow for a provider."""
    # Check auth rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not check_auth_rate_limit(client_ip):
        logger.warning(f"Auth rate limit exceeded for {client_ip}")
        raise HTTPException(
            status_code=429, detail="Too many authentication attempts. Please wait."
        )

    if provider not in providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    url = providers[provider].get_auth_url(add_new_account=add_account)
    if open_browser:
        webbrowser.open(url)
        return {"status": "ok", "message": "Browser opened for authentication"}
    return {"status": "ok", "url": url}


@api_v1.post("/auth/{provider}/logout", tags=["auth"])
async def logout(provider: str):
    """Logout from a provider and clear stored credentials."""
    if provider not in providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    success = providers[provider].logout()
    with _cached_limits_lock:
        if provider in cached_limits:
            del cached_limits[provider]
    return {"status": "ok" if success else "error"}


# ===== Multi-Account Endpoints =====


@api_v1.get("/accounts", tags=["accounts"])
async def get_accounts(provider: Optional[str] = None):
    """Get all registered accounts, optionally filtered by provider."""
    accounts = CredentialManager.get_accounts(provider)
    return {"accounts": accounts}


@api_v1.post("/accounts/{account_id}/activate", tags=["accounts"])
async def activate_account(account_id: str):
    """Set an account as the active account for its provider."""
    if not validate_account_id(account_id):
        raise HTTPException(status_code=400, detail="Invalid account_id format")
    success = CredentialManager.set_active_account(account_id)
    if success:
        # Clear cache to force refresh with new account
        with _cached_limits_lock:
            cached_limits.clear()
        await update_all_limits()
    return {"status": "ok" if success else "error"}


@api_v1.put("/accounts/{account_id}/name", tags=["accounts"])
async def update_account_name(
    account_id: str, name: str = Query(..., min_length=1, max_length=50)
):
    """Update the display name of an account."""
    if not validate_account_id(account_id):
        raise HTTPException(status_code=400, detail="Invalid account_id format")
    success = CredentialManager.update_account_name(account_id, name)
    return {"status": "ok" if success else "error"}


@api_v1.delete("/accounts/{account_id}", tags=["accounts"])
async def delete_account(account_id: str):
    """Delete an account and its stored credentials."""
    if not validate_account_id(account_id):
        raise HTTPException(status_code=400, detail="Invalid account_id format")
    # Check if this is the active account
    accounts = CredentialManager.get_accounts(provider=None)
    for acc in accounts:
        if acc["id"] == account_id and acc.get("is_active"):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete active account; activate another account first",
            )

    success = CredentialManager.delete_account(account_id)
    if success:
        with _cached_limits_lock:
            cached_limits.clear()
        await update_all_limits()
    return {"status": "ok" if success else "error"}


# Include API router
app.include_router(api_v1)


# ===== Root endpoints =====
@app.get("/")
async def root() -> dict:
    """Root endpoint with service info."""
    return {"status": "ok", "service": "aicap", "version": VERSION}


@app.get("/health", tags=["status"])
async def health_check():
    """Detailed health check endpoint."""
    checks = {
        "scheduler": scheduler.running,
        "providers": {},
        "storage": False,
    }

    # Check providers
    for name, provider in providers.items():
        checks["providers"][name] = {
            "authenticated": provider.is_authenticated(),
            "has_cached_limits": name in cached_limits,
        }

    # Check credential storage
    try:
        from .auth.credentials import CredentialManager

        accounts = CredentialManager.get_accounts()
        checks["storage"] = True
        checks["accounts_count"] = len(accounts)
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        checks["storage"] = False

    all_healthy = checks["scheduler"] and checks["storage"]

    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "last_update": last_update.isoformat() if last_update else None,
        "version": VERSION,
    }


@app.get("/metrics", tags=["status"])
async def get_metrics():
    """Get application metrics for monitoring."""
    return {
        "uptime_seconds": time.time() - app_start_time,
        "requests": {
            "rate_limited": sum(len(v) for v in rate_limit_storage.values()),
            "auth_rate_limited": sum(len(v) for v in auth_rate_limit_storage.values()),
        },
        "providers": {
            name: {
                "authenticated": p.is_authenticated(),
                "cached": name in cached_limits,
            }
            for name, p in providers.items()
        },
        "accounts_count": len(CredentialManager.get_accounts()),
        "last_update": last_update.isoformat() if last_update else None,
        "scheduler_running": scheduler.running,
    }


@app.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(
    request: Request,
    code: str = Query(..., min_length=10),
    state: str = Query(..., min_length=16),
):
    """OAuth callback handler with CSRF validation and rate limiting."""
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit callback attempts
    if not check_auth_rate_limit(client_ip):
        logger.warning(f"Auth callback rate limit exceeded for {client_ip}")
        return """
        <html>
            <head><title>Too Many Requests</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px; background: #0a0a12; color: #fff;">
                <h1 style="color: #f87171;">⚠️ Too Many Requests</h1>
                <p>Please wait a moment before trying again.</p>
            </body>
        </html>
        """

    # Validate state first (CSRF protection)
    state_data = oauth_state_manager.validate_state(state)
    if not state_data:
        logger.warning(f"Invalid OAuth state from {client_ip}: {state[:16]}...")
        return """
        <html>
            <head><title>Invalid State</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px; background: #0a0a12; color: #fff;">
                <h1 style="color: #f87171;">❌ Invalid or Expired Session</h1>
                <p>Please try logging in again from the application.</p>
            </body>
        </html>
        """

    for name, provider in providers.items():
        success = await provider.handle_callback(code, state)
        if success:
            logger.info(f"Successful OAuth callback for {name} from {client_ip}")
            limits = await provider.get_limits()
            with _cached_limits_lock:
                cached_limits[name] = limits
            return """
            <html>
                <head><title>Authentication Successful</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px; background: #0a0a12; color: #fff;">
                    <h1 style="color: #4ade80;">✅ Authentication Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                    <script>setTimeout(() => window.close(), 3000);</script>
                </body>
            </html>
            """

    logger.warning(f"OAuth callback failed for {client_ip}")
    return """
    <html>
        <head><title>Authentication Failed</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: #0a0a12; color: #fff;">
            <h1 style="color: #f87171;">❌ Authentication Failed</h1>
            <p>Invalid or expired authorization. Please try again.</p>
        </body>
    </html>
    """


# Legacy routes (for backward compatibility)
@app.get("/status", response_model=StatusResponse, deprecated=True)
async def get_status_legacy():
    return await get_status()


@app.get("/limits", deprecated=True)
async def get_all_limits_legacy():
    return await get_all_limits()


@app.get("/limits/{provider}", deprecated=True)
async def get_provider_limits_legacy(provider: str):
    return await get_provider_limits(provider)


@app.post("/limits/refresh", deprecated=True)
async def refresh_limits_legacy():
    return await refresh_limits()


@app.get("/auth/{provider}/login", deprecated=True)
async def login_legacy(
    request: Request, provider: str, open_browser: bool = Query(default=True)
):
    """Legacy login endpoint - use /api/v1/auth/{provider}/login instead."""
    return await login(
        request=request, provider=provider, open_browser=open_browser, add_account=False
    )


@app.post("/auth/{provider}/logout", deprecated=True)
async def logout_legacy(provider: str):
    return await logout(provider)


if __name__ == "__main__":
    import uvicorn

    # Validate host security before starting
    validate_host_security(API_HOST, AICAP_API_TOKEN)

    uvicorn.run(app, host=API_HOST, port=API_PORT)
