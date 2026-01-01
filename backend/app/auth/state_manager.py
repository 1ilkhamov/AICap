"""OAuth state management with CSRF protection."""

import secrets
import time
import hashlib
import hmac
import threading
from typing import Optional, Dict
from dataclasses import dataclass
import logging

from ..config import OAUTH_STATE_EXPIRATION

logger = logging.getLogger(__name__)

# HMAC signature truncation length (16 hex chars = 64 bits)
# Provides sufficient collision resistance for short-lived state tokens
STATE_SIGNATURE_LENGTH = 16


@dataclass
class StateData:
    """OAuth state data."""

    state: str
    created_at: int  # Unix timestamp as int for consistent HMAC verification
    add_new_account: bool
    nonce: str
    provider: str = "openai"  # Provider identifier for multi-provider support


class OAuthStateManager:
    """Manages OAuth state tokens with CSRF protection and expiration."""

    MAX_PENDING_STATES = 100  # Prevent memory exhaustion

    def __init__(self):
        self._pending_states: Dict[str, StateData] = {}
        self._secret = secrets.token_bytes(32)
        self._lock = threading.Lock()

    def create_state(self, add_new_account: bool = False, provider: str = "openai") -> str:
        """Create a new cryptographically secure state token."""
        # Generate state with HMAC for integrity
        # IMPORTANT: Capture timestamp ONCE and use for both signing and storing
        # to eliminate any boundary race between signing and storage
        nonce = secrets.token_hex(16)
        created_at = int(time.time())
        timestamp = str(created_at)
        message = f"{nonce}:{timestamp}".encode()
        signature = hmac.new(self._secret, message, hashlib.sha256).hexdigest()[:STATE_SIGNATURE_LENGTH]
        state = f"{nonce}:{signature}"

        with self._lock:
            # Clean up expired states first
            self._cleanup_expired_unsafe()

            # Enforce max pending states to prevent memory exhaustion
            if len(self._pending_states) >= self.MAX_PENDING_STATES:
                # Remove oldest states
                sorted_states = sorted(
                    self._pending_states.items(), key=lambda x: x[1].created_at
                )
                for old_state, _ in sorted_states[: len(sorted_states) // 2]:
                    del self._pending_states[old_state]
                logger.warning(f"Pruned {len(sorted_states) // 2} old OAuth states")

            self._pending_states[state] = StateData(
                state=state,
                created_at=created_at,  # Use same timestamp as HMAC signing
                add_new_account=add_new_account,
                nonce=nonce,
                provider=provider,
            )

        logger.debug(f"Created new OAuth state for provider: {provider}")
        return state

    def validate_state(self, state: str) -> Optional[StateData]:
        """Validate state token and return data if valid."""
        if not state or ":" not in state:
            logger.warning("Invalid state format")
            return None

        with self._lock:
            # Check if state exists
            state_data = self._pending_states.get(state)
            if not state_data:
                logger.warning("Unknown OAuth state received")
                return None

            # Check expiration
            if time.time() - state_data.created_at > OAUTH_STATE_EXPIRATION:
                logger.warning("Expired OAuth state received")
                del self._pending_states[state]
                return None

        # Verify HMAC integrity (outside lock for performance)
        try:
            nonce, signature = state.split(":")
            timestamp = str(
                state_data.created_at
            )  # Already int, consistent with creation
            message = f"{nonce}:{timestamp}".encode()
            expected_sig = hmac.new(self._secret, message, hashlib.sha256).hexdigest()[
                :STATE_SIGNATURE_LENGTH
            ]

            if not hmac.compare_digest(signature, expected_sig):
                logger.warning("State signature mismatch")
                return None
        except Exception as e:
            logger.warning(f"State validation error: {e}")
            return None

        return state_data

    def consume_state(self, state: str) -> bool:
        """Consume (invalidate) a state token after successful use."""
        with self._lock:
            if state in self._pending_states:
                del self._pending_states[state]
                logger.debug("OAuth state consumed successfully")
                return True
        return False

    def cleanup_expired(self) -> None:
        """Remove expired state tokens (thread-safe, for scheduler)."""
        with self._lock:
            self._cleanup_expired_unsafe()

    def _cleanup_expired_unsafe(self) -> None:
        """Remove expired state tokens (must hold lock)."""
        now = time.time()
        expired = [
            s
            for s, data in self._pending_states.items()
            if now - data.created_at > OAUTH_STATE_EXPIRATION
        ]
        for state in expired:
            del self._pending_states[state]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired states")


# Global instance
oauth_state_manager = OAuthStateManager()
