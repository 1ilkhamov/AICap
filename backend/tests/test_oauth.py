"""Tests for OAuth authentication."""

import pytest
import time
from unittest.mock import patch, AsyncMock, MagicMock

from app.auth.oauth import OpenAIOAuth, PKCEPair, TokenData
from app.auth.state_manager import OAuthStateManager


class TestPKCE:
    """Test PKCE generation."""

    def test_generate_pkce(self):
        """Test PKCE pair generation."""
        oauth = OpenAIOAuth()
        pkce = oauth._generate_pkce()

        assert isinstance(pkce, PKCEPair)
        assert len(pkce.verifier) > 20
        assert len(pkce.challenge) > 20
        assert pkce.verifier != pkce.challenge

    def test_pkce_uniqueness(self):
        """Test that PKCE pairs are unique."""
        oauth = OpenAIOAuth()
        pkce1 = oauth._generate_pkce()
        pkce2 = oauth._generate_pkce()

        assert pkce1.verifier != pkce2.verifier
        assert pkce1.challenge != pkce2.challenge


class TestStateManager:
    """Test OAuth state manager."""

    def test_create_state(self):
        """Test state creation."""
        manager = OAuthStateManager()
        state = manager.create_state()

        assert state is not None
        assert ":" in state
        assert len(state) > 20

    def test_validate_state(self):
        """Test state validation."""
        manager = OAuthStateManager()
        state = manager.create_state()

        data = manager.validate_state(state)
        assert data is not None
        assert data.state == state

    def test_invalid_state(self):
        """Test invalid state validation."""
        manager = OAuthStateManager()

        assert manager.validate_state("invalid") is None
        assert manager.validate_state("invalid:state") is None

    def test_consume_state(self):
        """Test state consumption."""
        manager = OAuthStateManager()
        state = manager.create_state()

        assert manager.consume_state(state) is True
        assert manager.validate_state(state) is None

    def test_state_expiration(self):
        """Test state expiration."""
        manager = OAuthStateManager()
        state = manager.create_state()

        # Manually expire the state
        manager._pending_states[state].created_at = int(time.time() - 700)

        assert manager.validate_state(state) is None


class TestAuthorizationFlow:
    """Test OAuth authorization flow."""

    def test_create_authorization_flow(self):
        """Test creating authorization flow."""
        oauth = OpenAIOAuth()
        flow = oauth.create_authorization_flow()

        assert flow.pkce is not None
        assert flow.state is not None
        assert flow.url is not None
        assert "code_challenge=" in flow.url
        assert "state=" in flow.url
        assert flow.created_at > 0

    def test_flow_expiration(self):
        """Test flow expiration check."""
        oauth = OpenAIOAuth()
        flow = oauth.create_authorization_flow()

        assert oauth._is_flow_valid(flow.state) is True

        # Simulate expired flow
        oauth._pending_flows[flow.state].created_at = time.time() - 700  # > 600 seconds
        assert oauth._is_flow_valid(flow.state) is False

    def test_state_mismatch(self):
        """Test state validation."""
        oauth = OpenAIOAuth()
        flow = oauth.create_authorization_flow()

        assert oauth._is_flow_valid(flow.state) is True
        assert oauth._is_flow_valid("wrong_state") is False


class TestTokenExchange:
    """Test token exchange."""

    @pytest.mark.asyncio
    async def test_exchange_code_no_flow(self):
        """Test exchange without pending flow."""
        oauth = OpenAIOAuth()
        result = await oauth.exchange_code("code", "state")
        assert result is None

    @pytest.mark.asyncio
    async def test_exchange_code_wrong_state(self):
        """Test exchange with wrong state."""
        oauth = OpenAIOAuth()
        oauth.create_authorization_flow()

        result = await oauth.exchange_code("valid_code_12345", "wrong_state_12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        """Test successful token exchange."""
        oauth = OpenAIOAuth()
        flow = oauth.create_authorization_flow()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_123",
            "refresh_token": "refresh_123",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            with patch(
                "app.auth.credentials.CredentialManager.save_tokens", return_value=True
            ):
                with patch(
                    "app.auth.state_manager.oauth_state_manager.validate_state"
                ) as mock_validate:
                    from app.auth.state_manager import StateData

                    mock_validate.return_value = StateData(
                        state=flow.state,
                        created_at=int(time.time()),
                        add_new_account=False,
                        nonce="test",
                    )
                    with patch(
                        "app.auth.state_manager.oauth_state_manager.consume_state"
                    ):
                        result = await oauth.exchange_code(
                            "valid_code_12345", flow.state
                        )

        assert result is not None
        assert result.access_token == "access_123"
        assert result.refresh_token == "refresh_123"

    @pytest.mark.asyncio
    async def test_exchange_code_uses_matching_flow(self):
        """Test multiple pending flows map to correct PKCE verifier."""
        oauth = OpenAIOAuth()
        flow_one = oauth.create_authorization_flow()
        flow_two = oauth.create_authorization_flow()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_456",
            "refresh_token": "refresh_456",
            "expires_in": 3600,
        }

        captured = {}

        async def capture_post(*args, **kwargs):
            captured["code_verifier"] = kwargs["data"]["code_verifier"]
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=capture_post
            )
            with patch(
                "app.auth.credentials.CredentialManager.save_tokens", return_value=True
            ):
                with patch(
                    "app.auth.state_manager.oauth_state_manager.validate_state"
                ) as mock_validate:
                    from app.auth.state_manager import StateData

                    mock_validate.side_effect = lambda state: StateData(
                        state=state,
                        created_at=int(time.time()),
                        add_new_account=False,
                        nonce="test",
                    )
                    with patch(
                        "app.auth.state_manager.oauth_state_manager.consume_state"
                    ):
                        result = await oauth.exchange_code(
                            "valid_code_12345", flow_two.state
                        )

        assert result is not None
        assert captured["code_verifier"] == flow_two.pkce.verifier
        assert flow_one.pkce.verifier != flow_two.pkce.verifier


class TestTokenRefresh:
    """Test token refresh behavior."""

    @pytest.mark.asyncio
    async def test_refresh_tokens_missing_refresh_token(self):
        """Test refresh uses stored refresh token when response omits it."""
        oauth = OpenAIOAuth()
        stored = {"refresh_token": "stored_refresh"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_789",
            "expires_in": 3600,
        }

        with patch(
            "app.auth.credentials.CredentialManager.get_tokens", return_value=stored
        ):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )
                with patch(
                    "app.auth.credentials.CredentialManager.save_tokens"
                ) as mock_save:
                    result = await oauth.refresh_tokens()

        assert result is not None
        assert result.refresh_token == "stored_refresh"
        mock_save.assert_called_once()


class TestAuthentication:
    """Test authentication state."""

    def test_is_authenticated_false(self):
        """Test unauthenticated state."""
        oauth = OpenAIOAuth()
        with patch(
            "app.auth.credentials.CredentialManager.has_tokens", return_value=False
        ):
            assert oauth.is_authenticated() is False

    def test_is_authenticated_true(self):
        """Test authenticated state."""
        oauth = OpenAIOAuth()
        with patch(
            "app.auth.credentials.CredentialManager.has_tokens", return_value=True
        ):
            assert oauth.is_authenticated() is True

    def test_logout(self):
        """Test logout."""
        oauth = OpenAIOAuth()
        with patch(
            "app.auth.credentials.CredentialManager.delete_tokens", return_value=True
        ):
            assert oauth.logout() is True


class TestStateManagerThreadSafety:
    """Test thread safety of state manager."""

    def test_max_pending_states(self):
        """Test that max pending states is enforced."""
        manager = OAuthStateManager()

        # Create more than MAX_PENDING_STATES
        for _ in range(manager.MAX_PENDING_STATES + 20):
            manager.create_state()

        # Should have pruned old states
        assert len(manager._pending_states) <= manager.MAX_PENDING_STATES

    def test_cleanup_expired_method(self):
        """Test explicit cleanup method."""
        manager = OAuthStateManager()
        state = manager.create_state()

        # Manually expire the state
        manager._pending_states[state].created_at = int(time.time() - 700)

        # Call cleanup
        manager.cleanup_expired()

        # State should be removed
        assert state not in manager._pending_states

    def test_create_validate_roundtrip_no_timestamp_mismatch(self):
        """Test that state create->validate roundtrip succeeds without timestamp boundary issues.

        This verifies the fix for the timestamp mismatch bug where create_state()
        captured timestamp twice (once for signing, once for storing), potentially
        causing HMAC verification failures at second boundaries.
        """
        manager = OAuthStateManager()

        # Create multiple states rapidly to test edge cases
        states = [manager.create_state() for _ in range(10)]

        # All should validate successfully immediately after creation
        for state in states:
            data = manager.validate_state(state)
            assert data is not None, (
                f"State validation failed unexpectedly: {state[:20]}..."
            )
            assert data.state == state
            assert isinstance(data.created_at, int)
            assert data.nonce is not None
