"""OAuth authentication for Google Antigravity."""

import hashlib
import base64
import secrets
import time
import asyncio
import threading
import logging
import httpx
from typing import Optional
from dataclasses import dataclass

from ..config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_AUTH_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_REDIRECT_URI,
    GOOGLE_SCOPES,
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
    add_new_account: bool = False


@dataclass
class TokenData:
    """OAuth token data."""

    access_token: str
    refresh_token: str
    expires_at: int


class GoogleOAuth:
    """Handles OAuth authentication for Google Antigravity."""

    PROVIDER = "antigravity"
    FLOW_EXPIRATION_SECONDS = 600  # 10 minutes

    def __init__(self):
        self._pending_flows: dict[str, AuthorizationFlow] = {}
        self._flow_lock = threading.Lock()

    @staticmethod
    def _generate_pkce() -> PKCEPair:
        """Generate PKCE verifier and challenge."""
        verifier = secrets.token_urlsafe(32)
        challenge_bytes = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode()
        return PKCEPair(verifier=verifier, challenge=challenge)

    @staticmethod
    def _generate_state() -> str:
        """Generate random state for OAuth flow."""
        return secrets.token_hex(16)

    def _cleanup_expired_flows_unsafe(self) -> None:
        now = time.time()
        expired_states = [
            state
            for state, flow in self._pending_flows.items()
            if now - flow.created_at > self.FLOW_EXPIRATION_SECONDS
        ]
        for state in expired_states:
            del self._pending_flows[state]

    def _is_flow_valid(self, state: str) -> bool:
        """Check if a pending flow is still valid (not expired)."""
        with self._flow_lock:
            self._cleanup_expired_flows_unsafe()
            return state in self._pending_flows

    def create_authorization_flow(
        self, add_new_account: bool = False
    ) -> AuthorizationFlow:
        """Create OAuth authorization flow with PKCE."""
        pkce = self._generate_pkce()
        state = oauth_state_manager.create_state(
            add_new_account=add_new_account, provider=self.PROVIDER
        )

        params = {
            "response_type": "code",
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "scope": GOOGLE_SCOPES,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }

        url = f"{GOOGLE_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())

        flow = AuthorizationFlow(
            pkce=pkce,
            state=state,
            url=url,
            created_at=time.time(),
            add_new_account=add_new_account,
        )
        with self._flow_lock:
            self._cleanup_expired_flows_unsafe()
            self._pending_flows[state] = flow
        return flow

    async def exchange_code(self, code: str, state: str) -> Optional[TokenData]:
        """Exchange authorization code for tokens."""
        logger.debug("Google OAuth: Exchange code called")

        # Atomically validate AND consume state to prevent replay attacks (TOCTOU fix)
        # Pass expected provider to ensure state is only consumed by the correct provider
        state_data = oauth_state_manager.validate_and_consume(
            state, expected_provider=self.PROVIDER
        )
        if not state_data:
            logger.warning("Invalid or expired OAuth state")
            return None

        with self._flow_lock:
            self._cleanup_expired_flows_unsafe()
            pending_flow = self._pending_flows.pop(state, None)

        if not pending_flow:
            logger.warning("No pending flow for state")
            return None

        if not code or len(code) < 10:
            logger.warning("Invalid authorization code format")
            return None

        add_new_account = state_data.add_new_account

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "code": code,
                        "code_verifier": pending_flow.pkce.verifier,
                        "redirect_uri": GOOGLE_REDIRECT_URI,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as e:
            logger.error(f"Network error during token exchange: {e}")
            return None

        if response.status_code != 200:
            # Redact sensitive response body - only log status code
            logger.error(f"Token exchange failed: {response.status_code}")
            return None

        try:
            data = response.json()
        except Exception:
            logger.error("Failed to parse token response")
            return None

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)

        if not access_token:
            logger.error("Invalid token response - missing access_token")
            return None

        tokens = TokenData(
            access_token=access_token,
            refresh_token=refresh_token or "",
            expires_at=int(time.time()) + expires_in,
        )

        tokens_dict = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at,
        }

        if add_new_account:
            account_id = CredentialManager.create_account(self.PROVIDER, tokens_dict)
            logger.info(f"Created new Antigravity account: {account_id}")
        else:
            save_result = CredentialManager.save_tokens(self.PROVIDER, tokens_dict)
            if not save_result:
                logger.error("Failed to save tokens")

        return tokens

    async def refresh_tokens(self) -> Optional[TokenData]:
        """Refresh access token using stored refresh token."""
        stored = CredentialManager.get_tokens(self.PROVIDER)
        if not stored:
            return None
        stored_refresh = stored.get("refresh_token")
        if not stored_refresh:
            return None

        max_retries = 3
        response: Optional[httpx.Response] = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        GOOGLE_TOKEN_URL,
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": stored_refresh,
                            "client_id": GOOGLE_CLIENT_ID,
                            "client_secret": GOOGLE_CLIENT_SECRET,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
            except httpx.RequestError as e:
                logger.warning(f"Token refresh attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return None

            if response.status_code == 200:
                break
            if response.status_code >= 500 and attempt < max_retries - 1:
                logger.warning("Server error on refresh, retrying...")
                await asyncio.sleep(1 * (attempt + 1))
                continue
            logger.warning(f"Token refresh failed: {response.status_code}")
            return None

        if response is None:
            return None

        try:
            data = response.json()
        except Exception:
            logger.error("Failed to parse refresh response")
            return None

        access_token = data.get("access_token")
        if not access_token:
            logger.error("Invalid refresh response - missing access_token")
            return None

        expires_in = data.get("expires_in", 3600)
        refresh_token = data.get("refresh_token") or stored_refresh

        tokens = TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=int(time.time()) + expires_in,
        )

        CredentialManager.save_tokens(
            self.PROVIDER,
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "expires_at": tokens.expires_at,
            },
        )

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
