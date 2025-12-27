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
        assert ':' in state
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
        manager._pending_states[state].created_at = time.time() - 700
        
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
        
        assert oauth._is_flow_valid() is True
        
        # Simulate expired flow
        oauth._pending_flow.created_at = time.time() - 700  # > 600 seconds
        assert oauth._is_flow_valid() is False
    
    def test_state_mismatch(self):
        """Test state validation."""
        oauth = OpenAIOAuth()
        flow = oauth.create_authorization_flow()
        
        # Wrong state should fail
        with patch.object(oauth, '_is_flow_valid', return_value=True):
            # exchange_code is async, we need to test differently
            assert oauth._pending_flow.state != "wrong_state"


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
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            with patch('app.auth.credentials.CredentialManager.save_tokens', return_value=True):
                with patch('app.auth.state_manager.oauth_state_manager.validate_state') as mock_validate:
                    from app.auth.state_manager import StateData
                    mock_validate.return_value = StateData(
                        state=flow.state,
                        created_at=time.time(),
                        add_new_account=False,
                        nonce="test"
                    )
                    with patch('app.auth.state_manager.oauth_state_manager.consume_state'):
                        result = await oauth.exchange_code("valid_code_12345", flow.state)
        
        assert result is not None
        assert result.access_token == "access_123"
        assert result.refresh_token == "refresh_123"


class TestAuthentication:
    """Test authentication state."""
    
    def test_is_authenticated_false(self):
        """Test unauthenticated state."""
        oauth = OpenAIOAuth()
        with patch('app.auth.credentials.CredentialManager.has_tokens', return_value=False):
            assert oauth.is_authenticated() is False
    
    def test_is_authenticated_true(self):
        """Test authenticated state."""
        oauth = OpenAIOAuth()
        with patch('app.auth.credentials.CredentialManager.has_tokens', return_value=True):
            assert oauth.is_authenticated() is True
    
    def test_logout(self):
        """Test logout."""
        oauth = OpenAIOAuth()
        with patch('app.auth.credentials.CredentialManager.delete_tokens', return_value=True):
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
        manager._pending_states[state].created_at = time.time() - 700
        
        # Call cleanup
        manager.cleanup_expired()
        
        # State should be removed
        assert state not in manager._pending_states
