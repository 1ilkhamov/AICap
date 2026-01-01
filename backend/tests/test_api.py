"""Tests for API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

TEST_API_TOKEN = "test-secret-token"


@pytest.fixture
def client(tmp_path):
    """Create test client with API token configured.

    Sets AICAP_API_TOKEN to bypass loopback-only middleware (which would
    reject TestClient since request.client is None). Tests that need to
    access protected endpoints must include the token header.
    """
    # Mock scheduler to avoid background tasks
    with patch("app.main.scheduler") as mock_scheduler:
        mock_scheduler.running = True
        mock_scheduler.start = MagicMock()
        mock_scheduler.shutdown = MagicMock()
        mock_scheduler.add_job = MagicMock()

        # Set API token to bypass loopback-only middleware
        # (TestClient has request.client=None which would be rejected otherwise)
        import app.main as main

        original_token = main.AICAP_API_TOKEN
        main.AICAP_API_TOKEN = TEST_API_TOKEN

        # Isolate CredentialManager storage to tmp dir to prevent network calls
        # when developer has local ~/.aicap/tokens.enc
        from app.auth.credentials import CredentialManager

        original_storage_dir = CredentialManager.STORAGE_DIR
        original_tokens_file = CredentialManager.TOKENS_FILE
        original_salt_file = CredentialManager.SALT_FILE

        CredentialManager.STORAGE_DIR = tmp_path / ".aicap"
        CredentialManager.TOKENS_FILE = CredentialManager.STORAGE_DIR / "tokens.enc"
        CredentialManager.SALT_FILE = CredentialManager.STORAGE_DIR / ".salt"

        try:
            from app.main import (
                app,
                rate_limit_storage,
                auth_rate_limit_storage,
                rate_limit_last_seen,
                auth_rate_limit_last_seen,
            )

            # Clear rate limit storage before each test
            rate_limit_storage.clear()
            auth_rate_limit_storage.clear()
            rate_limit_last_seen.clear()
            auth_rate_limit_last_seen.clear()

            with TestClient(app) as test_client:
                # Attach token for convenience
                test_client.token = TEST_API_TOKEN
                test_client.auth_headers = {"X-AICap-Token": TEST_API_TOKEN}
                yield test_client
        finally:
            # Restore original values
            main.AICAP_API_TOKEN = original_token
            CredentialManager.STORAGE_DIR = original_storage_dir
            CredentialManager.TOKENS_FILE = original_tokens_file
            CredentialManager.SALT_FILE = original_salt_file


class TestRootEndpoints:
    """Test root endpoints."""

    def test_root(self, client):
        """Test root endpoint."""
        response = client.get("/", headers=client.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "aicap"
        assert "version" in data

    def test_health(self, client):
        """Test health endpoint (exempt from auth)."""
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
        response = client.get("/api/v1/status", headers=client.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "providers" in data

    def test_limits(self, client):
        """Test limits endpoint."""
        response = client.get("/api/v1/limits", headers=client.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data

    def test_limits_unknown_provider(self, client):
        """Test limits for unknown provider."""
        response = client.get("/api/v1/limits/unknown", headers=client.auth_headers)
        assert response.status_code == 404

    def test_login_unknown_provider(self, client):
        """Test login for unknown provider."""
        response = client.get(
            "/api/v1/auth/unknown/login?open_browser=false", headers=client.auth_headers
        )
        assert response.status_code == 404

    def test_logout_unknown_provider(self, client):
        """Test logout for unknown provider."""
        response = client.post(
            "/api/v1/auth/unknown/logout", headers=client.auth_headers
        )
        assert response.status_code == 404


class TestApiTokenMiddleware:
    """Test optional API token middleware."""

    def test_is_exempt_path_function(self):
        """Test _is_exempt_path helper function for trailing slash handling."""
        from app.main import _is_exempt_path

        # Health check - with and without trailing slash
        assert _is_exempt_path("/health") is True
        assert _is_exempt_path("/health/") is True

        # Auth callback - with and without trailing slash
        assert _is_exempt_path("/auth/callback") is True
        assert _is_exempt_path("/auth/callback/") is True

        # Non-exempt paths
        assert _is_exempt_path("/") is False
        assert _is_exempt_path("/api/v1/status") is False
        assert _is_exempt_path("/auth/openai/login") is False
        assert _is_exempt_path("/metrics") is False

    def test_api_token_required_when_configured(self, client, monkeypatch):
        """Test API token is enforced for protected endpoints."""
        import app.main as main

        monkeypatch.setattr(main, "AICAP_API_TOKEN", "secret-token")

        response = client.get("/api/v1/status")
        assert response.status_code == 401

        response = client.get(
            "/api/v1/status", headers={"X-AICap-Token": "secret-token"}
        )
        assert response.status_code == 200

        response = client.get("/metrics")
        assert response.status_code == 401

        response = client.get("/metrics", headers={"X-AICap-Token": "secret-token"})
        assert response.status_code == 200

        response = client.get("/health")
        assert response.status_code == 200

    def test_docs_endpoints_protected_when_token_set(self, client, monkeypatch):
        """Test that /docs, /redoc, /openapi.json are protected when token is configured."""
        import app.main as main

        monkeypatch.setattr(main, "AICAP_API_TOKEN", "secret-token")

        # These should require token when AICAP_API_TOKEN is set
        # Include subpaths and trailing slashes
        protected_paths = [
            "/docs",
            "/docs/",
            "/docs/oauth2-redirect",
            "/redoc",
            "/redoc/",
            "/openapi.json",
        ]
        for path in protected_paths:
            response = client.get(path)
            assert response.status_code == 401, f"{path} should require token"

            response = client.get(path, headers={"X-AICap-Token": "secret-token"})
            # 200, 307 (redirect), or 404 (subpath not found) are acceptable with valid token
            assert response.status_code in (200, 307, 404), (
                f"{path} should be accessible with token (got {response.status_code})"
            )

    def test_requires_api_token_function(self):
        """Test _requires_api_token helper function directly."""
        from app.main import _requires_api_token

        # Should NOT require token (including trailing slashes)
        assert _requires_api_token("/health") is False
        assert _requires_api_token("/health/") is False
        assert _requires_api_token("/auth/callback") is False
        assert _requires_api_token("/auth/callback/") is False
        assert _requires_api_token("/") is False

        # Should require token - basic paths
        assert _requires_api_token("/docs") is True
        assert _requires_api_token("/redoc") is True
        assert _requires_api_token("/openapi.json") is True
        assert _requires_api_token("/api/v1/status") is True
        assert _requires_api_token("/api/v1/limits") is True
        assert _requires_api_token("/metrics") is True
        assert _requires_api_token("/status") is True
        assert _requires_api_token("/limits") is True
        assert _requires_api_token("/auth/openai/login") is True

        # Should require token - docs subpaths and trailing slashes
        assert _requires_api_token("/docs/") is True
        assert _requires_api_token("/docs/oauth2-redirect") is True
        assert _requires_api_token("/redoc/") is True


class TestLegacyEndpoints:
    """Test legacy (deprecated) endpoints still work."""

    def test_legacy_status(self, client):
        """Test legacy status endpoint."""
        response = client.get("/status", headers=client.auth_headers)
        assert response.status_code == 200

    def test_legacy_limits(self, client):
        """Test legacy limits endpoint."""
        response = client.get("/limits", headers=client.auth_headers)
        assert response.status_code == 200


class TestRateLimiting:
    """Test rate limiting."""

    def test_rate_limit_not_exceeded(self, client):
        """Test requests within rate limit."""
        for _ in range(5):
            response = client.get("/", headers=client.auth_headers)
            assert response.status_code == 200

    def test_rate_limit_exceeded(self, client, monkeypatch):
        """Test rate limit exceeded."""
        import app.main as main

        # Patch rate limit to a small value for deterministic test
        monkeypatch.setattr(main, "RATE_LIMIT_REQUESTS", 3)

        # Clear rate limit storage for this test
        main.rate_limit_storage.clear()
        main.rate_limit_last_seen.clear()

        # Make requests to exceed the patched limit (3)
        responses = []
        for _ in range(5):
            responses.append(client.get("/", headers=client.auth_headers))

        # At least one should be rate limited (429)
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, f"Expected 429 in {status_codes}"


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
        from app.main import (
            cleanup_rate_limit_storage,
            rate_limit_storage,
            rate_limit_last_seen,
            _rate_limit_lock,
        )
        import time

        # Add some old entries
        with _rate_limit_lock:
            old_ts = time.time() - 200
            new_ts = time.time()
            rate_limit_storage["old_ip"] = [old_ts]  # Old entry
            rate_limit_storage["new_ip"] = [new_ts]  # Fresh entry
            rate_limit_last_seen["old_ip"] = old_ts
            rate_limit_last_seen["new_ip"] = new_ts

        # Run cleanup
        cleanup_rate_limit_storage()

        # Old entry should be removed, new should remain
        with _rate_limit_lock:
            assert "old_ip" not in rate_limit_storage
            assert "new_ip" in rate_limit_storage


class TestMultiAccount:
    """Test multi-account management endpoints."""

    def test_get_accounts(self, client):
        """Test getting accounts list."""
        response = client.get("/api/v1/accounts", headers=client.auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)

    def test_get_accounts_by_provider(self, client):
        """Test getting accounts filtered by provider."""
        response = client.get(
            "/api/v1/accounts?provider=openai", headers=client.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "accounts" in data

    def test_activate_invalid_account_id_format(self, client):
        """Test activating account with invalid ID format."""
        # Too short
        response = client.post(
            "/api/v1/accounts/abc/activate", headers=client.auth_headers
        )
        assert response.status_code == 400
        assert "Invalid account_id format" in response.json()["detail"]

        # Too long
        response = client.post(
            "/api/v1/accounts/abcdef123456/activate", headers=client.auth_headers
        )
        assert response.status_code == 400

        # Invalid characters
        response = client.post(
            "/api/v1/accounts/ABCDEFGH/activate", headers=client.auth_headers
        )
        assert response.status_code == 400

    def test_activate_nonexistent_account(self, client):
        """Test activating non-existent account with valid format."""
        response = client.post(
            "/api/v1/accounts/deadbeef/activate", headers=client.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should return error status for non-existent account
        assert data.get("status") == "error"

    def test_update_account_name_validation(self, client):
        """Test account name update with validation."""
        # Test with empty name - should fail validation
        response = client.put(
            "/api/v1/accounts/deadbeef/name?name=", headers=client.auth_headers
        )
        assert response.status_code == 422  # Validation error

        # Test with too long name - should fail validation
        long_name = "x" * 51
        response = client.put(
            f"/api/v1/accounts/deadbeef/name?name={long_name}",
            headers=client.auth_headers,
        )
        assert response.status_code == 422

    def test_update_account_name_invalid_id(self, client):
        """Test account name update with invalid account ID."""
        response = client.put(
            "/api/v1/accounts/invalid/name?name=Test", headers=client.auth_headers
        )
        assert response.status_code == 400
        assert "Invalid account_id format" in response.json()["detail"]

    def test_delete_invalid_account_id_format(self, client):
        """Test deleting account with invalid ID format."""
        response = client.delete(
            "/api/v1/accounts/invalid", headers=client.auth_headers
        )
        assert response.status_code == 400
        assert "Invalid account_id format" in response.json()["detail"]

    def test_delete_nonexistent_account(self, client):
        """Test deleting non-existent account with valid format."""
        response = client.delete(
            "/api/v1/accounts/deadbeef", headers=client.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should return error status for non-existent account
        assert data.get("status") == "error"

    def test_delete_active_account_rejected(self, client, tmp_path):
        """Test that deleting the active account returns 409."""
        from app.auth.credentials import CredentialManager

        # Create an account which becomes active automatically
        account_id = CredentialManager.create_account(
            provider="openai",
            tokens={"access_token": "test", "refresh_token": "test"},
            name="Test Account",
        )

        # Attempt to delete the active account
        response = client.delete(
            f"/api/v1/accounts/{account_id}", headers=client.auth_headers
        )
        assert response.status_code == 409
        data = response.json()
        assert "active account" in data["detail"].lower()

    def test_delete_inactive_account_allowed(self, client, tmp_path):
        """Test that deleting an inactive account succeeds."""
        from app.auth.credentials import CredentialManager

        # Create two accounts
        account1_id = CredentialManager.create_account(
            provider="openai",
            tokens={"access_token": "test1", "refresh_token": "test1"},
            name="Account 1",
        )
        account2_id = CredentialManager.create_account(
            provider="openai",
            tokens={"access_token": "test2", "refresh_token": "test2"},
            name="Account 2",
        )

        # First account is active, second is not
        # Delete the inactive (second) account
        response = client.delete(
            f"/api/v1/accounts/{account2_id}", headers=client.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

        # Verify account is deleted
        accounts = CredentialManager.get_accounts()
        account_ids = [a["id"] for a in accounts]
        assert account2_id not in account_ids
        assert account1_id in account_ids


class TestHostSecurityHelpers:
    """Test startup security helper functions."""

    def test_validate_account_id_function(self):
        """Test validate_account_id helper function."""
        from app.main import validate_account_id

        # Valid account IDs (8 lowercase hex chars)
        assert validate_account_id("deadbeef") is True
        assert validate_account_id("12345678") is True
        assert validate_account_id("abcdef01") is True

        # Invalid account IDs
        assert validate_account_id("DEADBEEF") is False  # uppercase
        assert validate_account_id("abc") is False  # too short
        assert validate_account_id("abcdef0123") is False  # too long
        assert validate_account_id("ghijklmn") is False  # invalid chars
        assert validate_account_id("") is False  # empty
        assert validate_account_id("dead-beef") is False  # contains dash

    def test_request_id_middleware(self, client):
        """Test that request ID is added to responses."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "x-request-id" in response.headers
        # Should be 8 chars (uuid prefix)
        assert len(response.headers["x-request-id"]) == 8

    def test_request_id_passthrough(self, client):
        """Test that provided request ID is passed through."""
        custom_id = "custom01"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        assert response.headers["x-request-id"] == custom_id

    def test_is_loopback_client_function(self):
        """Test _is_loopback_client helper rejects unknown clients (fail-closed)."""
        from app.main import _is_loopback_client

        # Loopback addresses - allowed
        assert _is_loopback_client("127.0.0.1") is True
        assert _is_loopback_client("127.0.1.1") is True
        assert _is_loopback_client("localhost") is True
        assert _is_loopback_client("::1") is True
        assert _is_loopback_client("testclient") is True  # TestClient compatibility

        # Non-loopback / unknown - rejected (fail-closed)
        assert _is_loopback_client("unknown") is False
        assert _is_loopback_client("192.168.1.1") is False
        assert _is_loopback_client("10.0.0.1") is False
        assert _is_loopback_client("0.0.0.0") is False
        assert _is_loopback_client("") is False

    def test_is_loopback_host(self):
        """Test is_loopback_host function."""
        from app.config import is_loopback_host

        # Loopback addresses
        assert is_loopback_host("127.0.0.1") is True
        assert is_loopback_host("127.0.1.1") is True
        assert is_loopback_host("127.255.255.255") is True
        assert is_loopback_host("localhost") is True
        assert is_loopback_host("::1") is True

        # Non-loopback addresses
        assert is_loopback_host("0.0.0.0") is False
        assert is_loopback_host("192.168.1.1") is False
        assert is_loopback_host("10.0.0.1") is False
        assert is_loopback_host("example.com") is False

    def test_validate_host_security_loopback_no_token(self):
        """Test that loopback hosts don't require token."""
        from app.config import validate_host_security

        # Should not raise for loopback without token
        validate_host_security("127.0.0.1", None)
        validate_host_security("localhost", None)
        validate_host_security("::1", None)
        validate_host_security("127.0.1.1", "")

    def test_validate_host_security_non_loopback_with_token(self):
        """Test that non-loopback hosts with token are allowed."""
        from app.config import validate_host_security

        # Should not raise for non-loopback with token
        validate_host_security("0.0.0.0", "secret-token")
        validate_host_security("192.168.1.1", "my-token")

    def test_validate_host_security_non_loopback_no_token_exits(self):
        """Test that non-loopback without token causes exit."""
        from app.config import validate_host_security
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            validate_host_security("0.0.0.0", None)
        assert exc_info.value.code == 1

        with pytest.raises(SystemExit):
            validate_host_security("192.168.1.1", "")

        with pytest.raises(SystemExit):
            validate_host_security("example.com", None)
