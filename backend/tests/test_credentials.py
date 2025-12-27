"""Tests for credential management."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

# Patch storage dir before importing
TEST_DIR = Path(tempfile.mkdtemp())


@pytest.fixture(autouse=True)
def mock_storage_dir():
    """Use temporary directory for tests."""
    with patch('app.auth.credentials.CredentialManager.STORAGE_DIR', TEST_DIR):
        with patch('app.auth.credentials.CredentialManager.TOKENS_FILE', TEST_DIR / "tokens.enc"):
            with patch('app.auth.credentials.CredentialManager.SALT_FILE', TEST_DIR / ".salt"):
                yield
    # Cleanup
    for f in TEST_DIR.glob("*"):
        f.unlink()


class TestCredentialManager:
    """Test CredentialManager class."""
    
    def test_save_and_get_tokens(self, mock_storage_dir):
        """Test saving and retrieving tokens."""
        from app.auth.credentials import CredentialManager
        
        tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": 1234567890,
        }
        
        result = CredentialManager.save_tokens("test_provider", tokens)
        assert result is True
        
        retrieved = CredentialManager.get_tokens("test_provider")
        assert retrieved is not None
        assert retrieved["access_token"] == "test_access_token"
        assert retrieved["refresh_token"] == "test_refresh_token"
        assert retrieved["expires_at"] == 1234567890
    
    def test_has_tokens(self, mock_storage_dir):
        """Test checking if tokens exist."""
        from app.auth.credentials import CredentialManager
        
        assert CredentialManager.has_tokens("nonexistent") is False
        
        CredentialManager.save_tokens("test", {"access_token": "test"})
        assert CredentialManager.has_tokens("test") is True
    
    def test_delete_tokens(self, mock_storage_dir):
        """Test deleting tokens."""
        from app.auth.credentials import CredentialManager
        
        CredentialManager.save_tokens("test", {"access_token": "test"})
        assert CredentialManager.has_tokens("test") is True
        
        result = CredentialManager.delete_tokens("test")
        assert result is True
        assert CredentialManager.has_tokens("test") is False
    
    def test_multiple_providers(self, mock_storage_dir):
        """Test storing tokens for multiple providers."""
        from app.auth.credentials import CredentialManager
        
        CredentialManager.save_tokens("provider1", {"token": "token1"})
        CredentialManager.save_tokens("provider2", {"token": "token2"})
        
        assert CredentialManager.get_tokens("provider1")["token"] == "token1"
        assert CredentialManager.get_tokens("provider2")["token"] == "token2"
        
        CredentialManager.delete_tokens("provider1")
        assert CredentialManager.has_tokens("provider1") is False
        assert CredentialManager.has_tokens("provider2") is True
    
    def test_get_nonexistent_provider(self, mock_storage_dir):
        """Test getting tokens for nonexistent provider."""
        from app.auth.credentials import CredentialManager
        
        result = CredentialManager.get_tokens("nonexistent")
        assert result is None
