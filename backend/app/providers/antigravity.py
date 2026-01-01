"""Google Antigravity provider for fetching usage limits."""

import logging
import httpx
from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from ..config import ANTIGRAVITY_API_URL, is_google_oauth_configured
from ..auth.google_oauth import GoogleOAuth

logger = logging.getLogger(__name__)

# API URLs
LOAD_PROJECT_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"

# User agent to emulate Antigravity client
USER_AGENT = "antigravity/1.11.3 Windows/x64"


@dataclass
class ModelQuota:
    """Quota information for a single model."""
    model_name: str
    display_name: str
    remaining_fraction: float  # 0.0 to 1.0
    used_percent: float  # 0 to 100
    reset_time: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "display_name": self.display_name,
            "remaining_fraction": self.remaining_fraction,
            "used_percent": self.used_percent,
            "reset_time": self.reset_time.isoformat() if self.reset_time else None,
        }


@dataclass
class UsageLimits:
    """Usage limits data structure for Antigravity."""
    
    provider: str
    is_authenticated: bool
    
    account_id: Optional[str] = None
    email: Optional[str] = None
    
    # List of model quotas
    models: List[ModelQuota] = field(default_factory=list)
    
    # Aggregated usage (average or max across models)
    primary_used_percent: Optional[float] = None
    primary_reset_at: Optional[datetime] = None
    
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "is_authenticated": self.is_authenticated,
            "account_id": self.account_id,
            "email": self.email,
            "models": [m.to_dict() for m in self.models],
            "primary_used_percent": self.primary_used_percent,
            "primary_reset_at": self.primary_reset_at.isoformat() if self.primary_reset_at else None,
            "error": self.error,
        }


# Model display names mapping
MODEL_DISPLAY_NAMES = {
    "gemini-3-pro-high": "Gemini 3 Pro (High)",
    "gemini-3-pro-low": "Gemini 3 Pro (Low)",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-3-flash": "Gemini Flash",
    "gemini-3-pro-image": "Gemini Image",
    "claude-sonnet-4": "Claude Sonnet 4",
    "claude-sonnet-4-thinking": "Claude Sonnet 4 (Thinking)",
    "claude-sonnet-4-5": "Claude 4.5 Sonnet",
    "claude-sonnet-4-5-thinking": "Claude 4.5 Sonnet (Thinking)",
    "claude-3-7-sonnet": "Claude 3.7 Sonnet",
    "claude-3-7-sonnet-thinking": "Claude 3.7 Sonnet (Thinking)",
}


class AntigravityProvider:
    """Provider for Google Antigravity usage limits."""
    
    PROVIDER_NAME = "antigravity"
    
    def __init__(self):
        self.oauth = GoogleOAuth()
    
    async def _get_project_id(self, token: str) -> Optional[str]:
        """Fetch project ID from loadCodeAssist endpoint."""
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            }
            
            payload = {
                "metadata": {
                    "ideType": "ANTIGRAVITY"
                }
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    LOAD_PROJECT_URL,
                    headers=headers,
                    json=payload,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("cloudaicompanionProject")
                    
        except Exception as e:
            logger.debug(f"Failed to get project ID: {e}")
        
        return None
    
    def _parse_models_response(self, data: dict) -> List[ModelQuota]:
        """Parse fetchAvailableModels response into ModelQuota list."""
        models = []
        models_data = data.get("models", {})
        
        logger.debug(f"Parsing models response: {list(models_data.keys())}")
        
        for model_name, model_info in models_data.items():
            # Only include gemini and claude models
            if not ("gemini" in model_name.lower() or "claude" in model_name.lower()):
                continue
            
            quota_info = model_info.get("quotaInfo", {})
            logger.debug(f"Model {model_name} quotaInfo: {quota_info}")
            
            # Get remaining fraction
            # If remainingFraction is missing but resetTime exists = quota exhausted (0%)
            # If no quotaInfo at all = assume full (1.0)
            remaining = quota_info.get("remainingFraction")
            if remaining is None:
                if "resetTime" in quota_info:
                    # Has reset time but no remaining = exhausted
                    remaining = 0.0
                else:
                    # No quota info at all = unlimited/full
                    remaining = 1.0
            
            # Parse reset time
            reset_time = None
            reset_str = quota_info.get("resetTime")
            if reset_str:
                try:
                    reset_time = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            
            models.append(ModelQuota(
                model_name=model_name,
                display_name=MODEL_DISPLAY_NAMES.get(model_name, model_name),
                remaining_fraction=remaining,
                used_percent=round((1.0 - remaining) * 100, 1),
                reset_time=reset_time,
            ))
        
        # Sort by used_percent descending (most used first)
        models.sort(key=lambda m: m.used_percent, reverse=True)
        return models
    
    async def get_limits(self) -> UsageLimits:
        """Fetch current usage limits from Antigravity API."""
        if not is_google_oauth_configured():
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=False,
                error="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            )
        
        if not self.oauth.is_authenticated():
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=False,
                error="Not authenticated",
            )
        
        token = await self.oauth.get_valid_token()
        if not token:
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=False,
                error="Failed to get valid token",
            )
        
        try:
            # First get project ID
            project_id = await self._get_project_id(token)
            logger.debug(f"Got project ID: {project_id}")
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            }
            
            # Build payload with project if available
            payload = {}
            if project_id:
                payload["project"] = project_id
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    ANTIGRAVITY_API_URL,
                    headers=headers,
                    json=payload,
                )
                
                logger.debug(f"Antigravity API response status: {response.status_code}")
                
                if response.status_code == 401:
                    logger.warning("Antigravity token expired or invalid")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=False,
                        error="Session expired. Please reconnect.",
                    )
                
                if response.status_code == 403:
                    logger.warning("Antigravity API forbidden")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        error="Access forbidden. Check your Antigravity subscription.",
                    )
                
                if response.status_code == 429:
                    logger.warning("Rate limited by Antigravity")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        error="Rate limited. Try again later.",
                    )
                
                if response.status_code >= 500:
                    logger.warning(f"Antigravity server error: {response.status_code}")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        error="Service unavailable. Try again later.",
                    )
                
                if response.status_code != 200:
                    logger.warning(f"Antigravity API error: {response.status_code} - {response.text}")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        error=f"API error: {response.status_code}",
                    )
                
                data = response.json()
                logger.info(f"Antigravity API full response: {data}")
                models = self._parse_models_response(data)
                
                # Calculate aggregated usage (max used percent across all models)
                primary_used = max((m.used_percent for m in models), default=0)
                
                # Find earliest reset time
                reset_times = [m.reset_time for m in models if m.reset_time]
                primary_reset = min(reset_times) if reset_times else None
                
                return UsageLimits(
                    provider=self.PROVIDER_NAME,
                    is_authenticated=True,
                    models=models,
                    primary_used_percent=primary_used,
                    primary_reset_at=primary_reset,
                )
        
        except httpx.RequestError as e:
            logger.error(f"Network error: {e}")
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=True,
                error=f"Network error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"API error: {e}")
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=True,
                error=f"API error: {str(e)}",
            )
    
    def is_authenticated(self) -> bool:
        return self.oauth.is_authenticated()
    
    def get_auth_url(self, add_new_account: bool = False) -> str:
        if not is_google_oauth_configured():
            raise ValueError("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
        flow = self.oauth.create_authorization_flow(add_new_account=add_new_account)
        return flow.url
    
    async def handle_callback(self, code: str, state: str) -> bool:
        tokens = await self.oauth.exchange_code(code, state)
        return tokens is not None
    
    def logout(self) -> bool:
        return self.oauth.logout()
