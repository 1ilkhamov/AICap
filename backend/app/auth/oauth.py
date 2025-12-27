"""OAuth authentication for OpenAI/Codex."""

import hashlib
import base64
import secrets
import time
import asyncio
import logging
import httpx
from typing import Optional
from dataclasses import dataclass

from ..config import (
    OPENAI_CLIENT_ID,
    OPENAI_AUTHORIZE_URL,
    OPENAI_TOKEN_URL,
    OPENAI_REDIRECT_URI,
    OPENAI_SCOPE,
)
from .credentials import CredentialManager
from .state_manager import oauth_state_manager

logger = logging.getLogger(__name__)


@dataclass
class PKCEPair:
    """PKCE challenge and verifier pair."""
    verifier: str
    challenge: str


@dataclass
class AuthorizationFlow:
    """OAuth authorization flow data."""
    pkce: PKCEPair
    state: str
    url: str
    created_at: float
    add_new_account: bool = False  # Flag to add as new account


@dataclass
class TokenData:
    """OAuth token data."""
    access_token: str
    refresh_token: str
    expires_at: int


class OpenAIOAuth:
    """Handles OAuth authentication for OpenAI/Codex."""
    
    PROVIDER = "openai"
    FLOW_EXPIRATION_SECONDS = 600  # 10 minutes
    
    def __init__(self):
        self._pending_flow: Optional[AuthorizationFlow] = None
    
    @staticmethod
    def _generate_pkce() -> PKCEPair:
        """Generate PKCE verifier and challenge."""
        verifier = secrets.token_urlsafe(32)
        challenge_bytes = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode()
        return PKCEPair(verifier=verifier, challenge=challenge)
    
    @staticmethod
    def _generate_state() -> str:
        """Generate random state for OAuth flow."""
        return secrets.token_hex(16)
    
    def _is_flow_valid(self) -> bool:
        """Check if pending flow is still valid (not expired)."""
        if not self._pending_flow:
            return False
        return time.time() - self._pending_flow.created_at < self.FLOW_EXPIRATION_SECONDS
    
    def create_authorization_flow(self, add_new_account: bool = False) -> AuthorizationFlow:
        """Create OAuth authorization flow with CSRF-protected state."""
        pkce = self._generate_pkce()
        
        # Use secure state manager instead of simple random
        state = oauth_state_manager.create_state(add_new_account=add_new_account)
        
        params = {
            "response_type": "code",
            "client_id": OPENAI_CLIENT_ID,
            "redirect_uri": OPENAI_REDIRECT_URI,
            "scope": OPENAI_SCOPE,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
        }
        
        url = f"{OPENAI_AUTHORIZE_URL}?" + "&".join(
            f"{k}={v}" for k, v in params.items()
        )
        
        self._pending_flow = AuthorizationFlow(
            pkce=pkce, 
            state=state, 
            url=url,
            created_at=time.time(),
            add_new_account=add_new_account
        )
        return self._pending_flow
    
    async def exchange_code(self, code: str, state: str) -> Optional[TokenData]:
        """Exchange authorization code for tokens with proper state validation."""
        logger.debug(f"Exchange code called with state={state[:16]}...")
        
        # Validate state using secure state manager
        state_data = oauth_state_manager.validate_state(state)
        if not state_data:
            logger.warning("Invalid or expired OAuth state")
            return None
        
        if not self._pending_flow:
            logger.warning("No pending flow")
            return None
        
        if self._pending_flow.state != state:
            logger.warning("State mismatch in OAuth callback")
            return None
        
        # Validate code format (basic check)
        if not code or len(code) < 10:
            logger.warning("Invalid authorization code format")
            return None
        
        add_new_account = state_data.add_new_account
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    OPENAI_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": OPENAI_CLIENT_ID,
                        "code": code,
                        "code_verifier": self._pending_flow.pkce.verifier,
                        "redirect_uri": OPENAI_REDIRECT_URI,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as e:
            logger.error(f"Network error during token exchange: {e}")
            return None
        finally:
            self._pending_flow = None
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code}")
            return None
        
        try:
            data = response.json()
        except Exception:
            logger.error("Failed to parse token response")
            return None
        
        required_fields = ("access_token", "refresh_token", "expires_in")
        if not all(k in data for k in required_fields):
            logger.error("Invalid token response - missing fields")
            return None
        
        tokens = TokenData(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=int(time.time()) + data["expires_in"],
        )
        
        tokens_dict = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
        }
        
        # Check if adding new account or updating existing
        if add_new_account:
            account_id = CredentialManager.create_account(self.PROVIDER, tokens_dict)
            logger.info(f"Created new account: {account_id}")
        else:
            save_result = CredentialManager.save_tokens(self.PROVIDER, tokens_dict)
            if not save_result:
                logger.error("Failed to save tokens")
        
        # Consume the state to prevent replay attacks
        oauth_state_manager.consume_state(state)
        
        return tokens
    
    async def refresh_tokens(self) -> Optional[TokenData]:
        """Refresh access token using stored refresh token with retry."""
        stored = CredentialManager.get_tokens(self.PROVIDER)
        if not stored or "refresh_token" not in stored:
            return None
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        OPENAI_TOKEN_URL,
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": stored["refresh_token"],
                            "client_id": OPENAI_CLIENT_ID,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
            except httpx.RequestError as e:
                logger.warning(f"Token refresh attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                    continue
                return None
            
            if response.status_code == 200:
                break
            elif response.status_code >= 500 and attempt < max_retries - 1:
                logger.warning("Server error on refresh, retrying...")
                await asyncio.sleep(1 * (attempt + 1))
                continue
            else:
                logger.warning(f"Token refresh failed: {response.status_code}")
                return None
        
        try:
            data = response.json()
        except Exception:
            logger.error("Failed to parse refresh response")
            return None
        
        tokens = TokenData(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=int(time.time()) + data["expires_in"],
        )
        
        CredentialManager.save_tokens(self.PROVIDER, {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
        })
        
        return tokens
    
    async def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary."""
        stored = CredentialManager.get_tokens(self.PROVIDER)
        if not stored:
            return None
        
        # Check if token is expired (with 5 min buffer)
        if stored.get("expires_at", 0) < time.time() + 300:
            tokens = await self.refresh_tokens()
            if tokens:
                return tokens.access_token
            return None
        
        return stored.get("access_token")
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return CredentialManager.has_tokens(self.PROVIDER)
    
    def logout(self) -> bool:
        """Remove stored tokens."""
        return CredentialManager.delete_tokens(self.PROVIDER)
