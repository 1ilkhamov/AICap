"""FastAPI application for AICap."""

import logging
import time
import webbrowser
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

from .providers.openai_codex import OpenAICodexProvider, UsageLimits
from .auth.credentials import CredentialManager
from .auth.state_manager import oauth_state_manager
from .config import (
    UPDATE_INTERVAL_MINUTES,
    CORS_ORIGINS,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW,
    AUTH_RATE_LIMIT_REQUESTS,
    AUTH_RATE_LIMIT_WINDOW,
)

logger = logging.getLogger(__name__)

# Global State
providers = {"openai": OpenAICodexProvider()}
cached_limits: dict[str, UsageLimits] = {}
last_update: Optional[datetime] = None
scheduler = AsyncIOScheduler()

# Thread-safe rate limiting
_rate_limit_lock = threading.Lock()
_auth_rate_limit_lock = threading.Lock()
rate_limit_storage: dict[str, list[float]] = defaultdict(list)
auth_rate_limit_storage: dict[str, list[float]] = defaultdict(list)
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
            return False
        rate_limit_storage[client_ip].append(now)
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
            return False
        auth_rate_limit_storage[client_ip].append(now)
        return True


def cleanup_rate_limit_storage() -> None:
    """Periodic cleanup of rate limit storage to prevent memory leaks."""
    now = time.time()
    
    with _rate_limit_lock:
        expired_ips = [
            ip for ip, timestamps in rate_limit_storage.items()
            if not timestamps or max(timestamps) < now - RATE_LIMIT_WINDOW * 2
        ]
        for ip in expired_ips:
            del rate_limit_storage[ip]
    
    with _auth_rate_limit_lock:
        expired_ips = [
            ip for ip, timestamps in auth_rate_limit_storage.items()
            if not timestamps or max(timestamps) < now - AUTH_RATE_LIMIT_WINDOW * 2
        ]
        for ip in expired_ips:
            del auth_rate_limit_storage[ip]
    
    if expired_ips:
        logger.debug(f"Cleaned up rate limit entries for {len(expired_ips)} IPs")


async def update_all_limits():
    """Update limits for all authenticated providers."""
    global cached_limits, last_update
    for name, provider in providers.items():
        if provider.is_authenticated():
            try:
                cached_limits[name] = await provider.get_limits()
            except Exception as e:
                logger.error(f"Failed to update limits for {name}: {e}")
    last_update = datetime.now()
    logger.info(f"Updated limits for {len(cached_limits)} providers")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    scheduler.add_job(update_all_limits, "interval", minutes=UPDATE_INTERVAL_MINUTES, id="update_limits")
    scheduler.add_job(cleanup_rate_limit_storage, "interval", minutes=10, id="cleanup_rate_limits")
    scheduler.add_job(oauth_state_manager.cleanup_expired, "interval", minutes=5, id="cleanup_oauth_states")
    scheduler.start()
    logger.info("Scheduler started with cleanup jobs")
    await update_all_limits()
    yield
    scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")


app = FastAPI(
    title="AICap",
    description="Track API usage limits for AI services like OpenAI Codex",
    version="1.1.0",
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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    return await call_next(request)


class StatusResponse(BaseModel):
    status: str
    providers: dict[str, bool]
    last_update: Optional[str]


# ===== API v1 Router =====
from fastapi import APIRouter
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
async def get_all_limits():
    """Get usage limits for all authenticated providers."""
    return {
        "last_update": last_update.isoformat() if last_update else None,
        "providers": {name: limits.to_dict() for name, limits in cached_limits.items()},
    }


@api_v1.get("/limits/{provider}", tags=["limits"])
async def get_provider_limits(provider: str):
    """Get usage limits for a specific provider."""
    if provider not in providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    if provider in cached_limits:
        return cached_limits[provider].to_dict()
    limits = await providers[provider].get_limits()
    cached_limits[provider] = limits
    return limits.to_dict()


@api_v1.post("/limits/refresh", tags=["limits"])
async def refresh_limits():
    """Force refresh limits for all authenticated providers."""
    await update_all_limits()
    return {"status": "ok", "last_update": last_update.isoformat() if last_update else None}


@api_v1.get("/auth/{provider}/login", tags=["auth"])
async def login(request: Request, provider: str, open_browser: bool = Query(default=True), add_account: bool = Query(default=False)):
    """Start OAuth authentication flow for a provider."""
    # Check auth rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not check_auth_rate_limit(client_ip):
        logger.warning(f"Auth rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many authentication attempts. Please wait.")
    
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
    success = CredentialManager.set_active_account(account_id)
    if success:
        # Clear cache to force refresh with new account
        cached_limits.clear()
        await update_all_limits()
    return {"status": "ok" if success else "error"}


@api_v1.put("/accounts/{account_id}/name", tags=["accounts"])
async def update_account_name(account_id: str, name: str = Query(..., min_length=1, max_length=50)):
    """Update the display name of an account."""
    success = CredentialManager.update_account_name(account_id, name)
    return {"status": "ok" if success else "error"}


@api_v1.delete("/accounts/{account_id}", tags=["accounts"])
async def delete_account(account_id: str):
    """Delete an account and its stored credentials."""
    success = CredentialManager.delete_account(account_id)
    if success:
        cached_limits.clear()
        await update_all_limits()
    return {"status": "ok" if success else "error"}


# Include API router
app.include_router(api_v1)


# ===== Root endpoints =====
@app.get("/")
async def root():
    return {"status": "ok", "service": "aicap", "version": "1.1.0"}


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
        "version": "1.1.0",
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
async def auth_callback(request: Request, code: str = Query(..., min_length=10), state: str = Query(..., min_length=16)):
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
            cached_limits[name] = await provider.get_limits()
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
async def login_legacy(provider: str, open_browser: bool = Query(default=True)):
    return await login(provider, open_browser)


@app.post("/auth/{provider}/logout", deprecated=True)
async def logout_legacy(provider: str):
    return await logout(provider)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=1455)
