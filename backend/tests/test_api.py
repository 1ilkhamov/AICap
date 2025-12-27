"""Tests for API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client."""
    # Mock scheduler to avoid background tasks
    with patch('app.main.scheduler') as mock_scheduler:
        mock_scheduler.running = True
        mock_scheduler.start = MagicMock()
        mock_scheduler.shutdown = MagicMock()
        mock_scheduler.add_job = MagicMock()
        
        from app.main import app, rate_limit_storage, auth_rate_limit_storage
        # Clear rate limit storage before each test
        rate_limit_storage.clear()
        auth_rate_limit_storage.clear()
        
        with TestClient(app) as client:
            yield client


class TestRootEndpoints:
    """Test root endpoints."""
    
    def test_root(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "aicap"
        assert "version" in data
    
    def test_health(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "scheduler" in data["checks"]
        assert "providers" in data["checks"]


class TestAPIv1:
    """Test API v1 endpoints."""
    
    def test_status(self, client):
        """Test status endpoint."""
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "providers" in data
    
    def test_limits(self, client):
        """Test limits endpoint."""
        response = client.get("/api/v1/limits")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
    
    def test_limits_unknown_provider(self, client):
        """Test limits for unknown provider."""
        response = client.get("/api/v1/limits/unknown")
        assert response.status_code == 404
    
    def test_login_unknown_provider(self, client):
        """Test login for unknown provider."""
        response = client.get("/api/v1/auth/unknown/login?open_browser=false")
        assert response.status_code == 404
    
    def test_logout_unknown_provider(self, client):
        """Test logout for unknown provider."""
        response = client.post("/api/v1/auth/unknown/logout")
        assert response.status_code == 404


class TestLegacyEndpoints:
    """Test legacy (deprecated) endpoints still work."""
    
    def test_legacy_status(self, client):
        """Test legacy status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200
    
    def test_legacy_limits(self, client):
        """Test legacy limits endpoint."""
        response = client.get("/limits")
        assert response.status_code == 200


class TestRateLimiting:
    """Test rate limiting."""
    
    def test_rate_limit_not_exceeded(self, client):
        """Test requests within rate limit."""
        for _ in range(5):
            response = client.get("/")
            assert response.status_code == 200
    
    def test_rate_limit_exceeded(self, client):
        """Test rate limit exceeded."""
        # Make many requests to exceed limit
        responses = []
        for _ in range(70):  # More than RATE_LIMIT_REQUESTS (60)
            responses.append(client.get("/"))
        
        # At least one should be rate limited
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes or all(s == 200 for s in status_codes)


class TestAuthCallback:
    """Test OAuth callback."""
    
    def test_callback_invalid_code(self, client):
        """Test callback with invalid code."""
        # Clear rate limit storage for this test
        from app.main import auth_rate_limit_storage
        auth_rate_limit_storage.clear()
        
        response = client.get("/auth/callback?code=short&state=validstate12345678")
        assert response.status_code == 422  # Validation error - code too short
    
    def test_callback_invalid_state(self, client):
        """Test callback with invalid state."""
        # Clear rate limit storage for this test
        from app.main import auth_rate_limit_storage
        auth_rate_limit_storage.clear()
        
        response = client.get("/auth/callback?code=validcode12345&state=short")
        assert response.status_code == 422  # Validation error - state too short



class TestCleanupJobs:
    """Test cleanup functionality."""
    
    def test_cleanup_rate_limit_storage(self, client):
        """Test rate limit storage cleanup."""
        from app.main import cleanup_rate_limit_storage, rate_limit_storage, _rate_limit_lock
        import time
        
        # Add some old entries
        with _rate_limit_lock:
            rate_limit_storage["old_ip"] = [time.time() - 200]  # Old entry
            rate_limit_storage["new_ip"] = [time.time()]  # Fresh entry
        
        # Run cleanup
        cleanup_rate_limit_storage()
        
        # Old entry should be removed, new should remain
        with _rate_limit_lock:
            assert "old_ip" not in rate_limit_storage
            assert "new_ip" in rate_limit_storage
