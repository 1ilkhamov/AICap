"""OpenAI/Codex API provider for fetching usage limits."""

import base64
import json
import logging
import re
import httpx
from typing import Optional, Set
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

from ..config import CODEX_BASE_URL, CODEX_MODEL_NAME
from ..auth.oauth import OpenAIOAuth

logger = logging.getLogger(__name__)

# GitHub URLs for Codex instructions
GITHUB_RELEASES_URL = "https://github.com/openai/codex/releases/latest"
CODEX_PROMPT_URL_TEMPLATE = "https://raw.githubusercontent.com/openai/codex/{tag}/codex-rs/core/gpt_5_codex_prompt.md"

# Cache directory
CACHE_DIR = Path.home() / ".aicap" / "cache"

# Security constants
ALLOWED_HOSTS: Set[str] = {"github.com", "raw.githubusercontent.com"}
MAX_RESPONSE_SIZE_BYTES = 1024 * 1024  # 1 MB limit for fetched instructions
FETCH_TIMEOUT_SECONDS = 15.0

# Validation patterns
ACCOUNT_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")
# Strict pattern for release tags: allows semver-like tags with optional prefix (e.g., "v1.0.0", "rust-v0.43.0")
TAG_PATTERN = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9._]{0,127}$")


@dataclass
class RateLimitInfo:
    """Rate limit information from Codex headers."""

    plan_type: Optional[str] = None
    primary_used_percent: Optional[float] = None
    primary_window_minutes: Optional[int] = None
    primary_reset_at: Optional[int] = None
    primary_reset_after_seconds: Optional[int] = None
    secondary_used_percent: Optional[float] = None
    secondary_window_minutes: Optional[int] = None
    secondary_reset_at: Optional[int] = None
    secondary_reset_after_seconds: Optional[int] = None


@dataclass
class UsageLimits:
    """Usage limits data structure."""

    provider: str
    is_authenticated: bool

    account_id: Optional[str] = None
    email: Optional[str] = None
    plan_type: Optional[str] = None

    primary_used_percent: Optional[float] = None
    primary_window_minutes: Optional[int] = None
    primary_reset_at: Optional[datetime] = None

    secondary_used_percent: Optional[float] = None
    secondary_window_minutes: Optional[int] = None
    secondary_reset_at: Optional[datetime] = None

    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "is_authenticated": self.is_authenticated,
            "account_id": self.account_id,
            "email": self.email,
            "plan_type": self.plan_type,
            "primary_used_percent": self.primary_used_percent,
            "primary_window_minutes": self.primary_window_minutes,
            "primary_reset_at": self.primary_reset_at.isoformat()
            if self.primary_reset_at
            else None,
            "secondary_used_percent": self.secondary_used_percent,
            "secondary_window_minutes": self.secondary_window_minutes,
            "secondary_reset_at": self.secondary_reset_at.isoformat()
            if self.secondary_reset_at
            else None,
            "error": self.error,
        }


def _safe_float(value: Optional[str]) -> Optional[float]:
    """Safely convert string to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Optional[str]) -> Optional[int]:
    """Safely convert string to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class OpenAICodexProvider:
    """Provider for OpenAI/Codex usage limits."""

    PROVIDER_NAME = "openai"
    CACHE_TTL_SECONDS = 900  # 15 minutes

    def __init__(self):
        self.oauth = OpenAIOAuth()

    def _decode_jwt(self, token: str) -> Optional[dict]:
        """Decode JWT token to extract payload (without cryptographic verification).

        WARNING: This decoding is NOT verified. The JWT signature is not checked.
        Claims extracted here should be treated as UNTRUSTED metadata only and
        must NOT be used to affect upstream API behavior or security decisions.
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
        except Exception:
            return None

    def _get_account_info(self, token: str) -> dict:
        """Extract account info from JWT token for display purposes only.

        WARNING: These values come from an unverified JWT decode and are
        best-effort metadata only. They should NOT be used for authentication
        or to affect upstream API requests (e.g., setting headers).

        Returns:
            dict with optional 'account_id' and 'email' fields.
            Values are validated for format before being returned.
        """
        payload = self._decode_jwt(token)
        if not payload:
            return {}

        result = {}

        # Extract email if present and looks valid
        email = payload.get("email")
        if email and isinstance(email, str) and "@" in email and len(email) <= 254:
            result["email"] = email

        # Extract account_id if present and matches expected format
        auth_data = payload.get("https://api.openai.com/auth", {})
        account_id = auth_data.get("chatgpt_account_id")
        if account_id and isinstance(account_id, str):
            # Validate format: must be UUID-like or hex string
            # Accept common formats but log if unexpected
            if ACCOUNT_ID_PATTERN.match(account_id) or self._is_valid_uuid_format(
                account_id
            ):
                result["account_id"] = account_id
            else:
                logger.debug(
                    f"Unexpected account_id format from JWT (not using): {account_id[:16]}..."
                )

        return result

    def _is_valid_uuid_format(self, value: str) -> bool:
        """Check if value looks like a UUID (with or without hyphens)."""
        # UUID with hyphens: 8-4-4-4-12 hex chars
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        # UUID without hyphens: 32 hex chars
        uuid_no_dash = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
        return bool(uuid_pattern.match(value) or uuid_no_dash.match(value))

    def _validate_url_host(self, url: str) -> bool:
        """Validate that a URL's host is in the allowed list (SSRF protection)."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("https",):
                return False
            if parsed.hostname not in ALLOWED_HOSTS:
                return False
            return True
        except Exception:
            return False

    def _validate_tag(self, tag: str) -> bool:
        """Validate release tag format to prevent path traversal and injection."""
        if not tag or not isinstance(tag, str):
            return False
        # Reject path traversal attempts
        if ".." in tag or "/" in tag or "\\" in tag:
            return False
        # Must match strict pattern
        return bool(TAG_PATTERN.match(tag))

    def _safe_cache_path(self, filename: str) -> Optional[Path]:
        """Safely construct a cache file path, ensuring it stays within CACHE_DIR."""
        try:
            # Sanitize filename: only allow alphanumeric, dash, underscore, dot
            safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
            if not safe_filename or safe_filename.startswith("."):
                return None

            cache_path = (CACHE_DIR / safe_filename).resolve()
            cache_dir_resolved = CACHE_DIR.resolve()

            # Ensure resolved path is within cache directory
            if not str(cache_path).startswith(str(cache_dir_resolved)):
                logger.warning(f"Path traversal attempt blocked: {filename}")
                return None

            return cache_path
        except Exception as e:
            logger.warning(f"Failed to construct safe cache path: {e}")
            return None

    async def _get_latest_release_tag(self) -> str:
        """Get latest Codex release tag from GitHub with SSRF protection."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(GITHUB_RELEASES_URL)
                current_url = GITHUB_RELEASES_URL

                # Handle redirects manually with allowlist checks
                max_redirects = 10
                redirect_count = 0
                while (
                    response.status_code in (301, 302, 303, 307, 308)
                    and redirect_count < max_redirects
                ):
                    redirect_count += 1
                    location = response.headers.get("location")
                    if not location:
                        logger.warning("Redirect response missing Location header")
                        return "rust-v0.43.0"  # Fallback

                    # Support relative Location headers by resolving against current URL
                    absolute_location = urljoin(current_url, location)

                    # SSRF protection: validate redirect target BEFORE following
                    if not self._validate_url_host(absolute_location):
                        logger.warning(
                            f"Redirect to untrusted host blocked: {absolute_location}"
                        )
                        return "rust-v0.43.0"  # Fallback

                    response = await client.get(absolute_location)
                    current_url = absolute_location

                if redirect_count >= max_redirects:
                    logger.warning("Too many redirects, aborting")
                    return "rust-v0.43.0"  # Fallback

                final_url = str(response.url)

                if "/tag/" in final_url:
                    tag = final_url.split("/tag/")[-1]
                    # Validate tag format
                    if self._validate_tag(tag):
                        return tag
                    else:
                        logger.warning(f"Invalid tag format rejected: {tag[:50]}")
        except Exception as e:
            logger.warning(f"Failed to get latest release tag: {e}")
        return "rust-v0.43.0"  # Fallback

    async def _get_codex_instructions(self) -> str:
        """Fetch Codex instructions from GitHub with caching and security limits."""
        cache_file = self._safe_cache_path("codex-instructions.md")

        # Use cached if exists and fresh
        if cache_file and cache_file.exists():
            try:
                mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                age_seconds = (datetime.now() - mtime).total_seconds()
                if age_seconds < self.CACHE_TTL_SECONDS:
                    return cache_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug(f"Cache read error: {e}")

        try:
            tag = await self._get_latest_release_tag()

            # Tag is already validated in _get_latest_release_tag, but double-check
            if not self._validate_tag(tag):
                raise ValueError(f"Invalid tag format: {tag[:50]}")

            url = CODEX_PROMPT_URL_TEMPLATE.format(tag=tag)

            # Validate constructed URL
            if not self._validate_url_host(url):
                raise ValueError(f"Constructed URL has invalid host: {url}")

            logger.debug(f"Fetching instructions from: {url}")

            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
                # Use streaming to enforce size limit before loading into memory
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.warning(f"GitHub returned: {response.status_code}")
                        raise Exception(
                            f"GitHub returned status {response.status_code}"
                        )

                    # Check Content-Length header if available
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > MAX_RESPONSE_SIZE_BYTES:
                        raise ValueError(f"Response too large: {content_length} bytes")

                    # Read with size limit
                    chunks = []
                    total_size = 0
                    async for chunk in response.aiter_bytes():
                        total_size += len(chunk)
                        if total_size > MAX_RESPONSE_SIZE_BYTES:
                            raise ValueError(
                                f"Response exceeded size limit of {MAX_RESPONSE_SIZE_BYTES} bytes"
                            )
                        chunks.append(chunk)

                    instructions = b"".join(chunks).decode("utf-8")

                    # Cache the instructions
                    if cache_file:
                        CACHE_DIR.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(instructions, encoding="utf-8")
                        logger.debug(
                            f"Instructions cached, length: {len(instructions)}"
                        )

                    return instructions

        except Exception as e:
            logger.warning(f"Failed to fetch instructions: {e}")

        # Return cached if available (even if stale)
        if cache_file and cache_file.exists():
            try:
                return cache_file.read_text(encoding="utf-8")
            except Exception:
                pass

        raise Exception("Could not load Codex instructions")

    def _parse_rate_limit_headers(self, headers) -> RateLimitInfo:
        """Parse Codex rate limit headers."""
        return RateLimitInfo(
            plan_type=headers.get("x-codex-plan-type"),
            primary_used_percent=_safe_float(
                headers.get("x-codex-primary-used-percent")
            ),
            primary_window_minutes=_safe_int(
                headers.get("x-codex-primary-window-minutes")
            ),
            primary_reset_at=_safe_int(headers.get("x-codex-primary-reset-at")),
            primary_reset_after_seconds=_safe_int(
                headers.get("x-codex-primary-reset-after-seconds")
            ),
            secondary_used_percent=_safe_float(
                headers.get("x-codex-secondary-used-percent")
            ),
            secondary_window_minutes=_safe_int(
                headers.get("x-codex-secondary-window-minutes")
            ),
            secondary_reset_at=_safe_int(headers.get("x-codex-secondary-reset-at")),
            secondary_reset_after_seconds=_safe_int(
                headers.get("x-codex-secondary-reset-after-seconds")
            ),
        )

    async def get_limits(self) -> UsageLimits:
        """Fetch current usage limits by making a test request to Codex API."""
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

        account_info = self._get_account_info(token)

        try:
            instructions = await self._get_codex_instructions()

            # NOTE: We intentionally do NOT set chatgpt-account-id header from
            # unverified JWT claims. The account_id from _get_account_info is
            # best-effort metadata only and should not affect upstream requests.
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "responses=experimental",
                "originator": "codex_cli_rs",
                "Accept": "text/event-stream",
            }

            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{CODEX_BASE_URL}/codex/responses",
                    headers=headers,
                    json={
                        "model": CODEX_MODEL_NAME,
                        "instructions": instructions,
                        "input": [
                            {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": "say hi"}],
                            }
                        ],
                        "stream": True,
                        "store": False,
                        "reasoning": {"effort": "low", "summary": "auto"},
                        "text": {"verbosity": "medium"},
                        "include": ["reasoning.encrypted_content"],
                    },
                )

                logger.debug(f"Response status: {response.status_code}")

                if response.status_code == 401:
                    logger.warning("Token expired or invalid")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=False,
                        error="Session expired. Please reconnect.",
                    )

                if response.status_code == 429:
                    logger.warning("Rate limited by OpenAI")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        account_id=account_info.get("account_id"),
                        email=account_info.get("email"),
                        error="Rate limited. Try again later.",
                    )

                if response.status_code >= 500:
                    logger.warning(f"OpenAI server error: {response.status_code}")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        account_id=account_info.get("account_id"),
                        email=account_info.get("email"),
                        error="OpenAI service unavailable. Try again later.",
                    )

                if response.status_code != 200:
                    logger.warning(f"API error: {response.status_code}")
                    return UsageLimits(
                        provider=self.PROVIDER_NAME,
                        is_authenticated=True,
                        account_id=account_info.get("account_id"),
                        email=account_info.get("email"),
                        error=f"API error: {response.status_code}",
                    )

                rate_info = self._parse_rate_limit_headers(response.headers)

                return UsageLimits(
                    provider=self.PROVIDER_NAME,
                    is_authenticated=True,
                    account_id=account_info.get("account_id"),
                    email=account_info.get("email"),
                    plan_type=rate_info.plan_type,
                    primary_used_percent=rate_info.primary_used_percent,
                    primary_window_minutes=rate_info.primary_window_minutes,
                    primary_reset_at=datetime.fromtimestamp(rate_info.primary_reset_at)
                    if rate_info.primary_reset_at
                    else None,
                    secondary_used_percent=rate_info.secondary_used_percent,
                    secondary_window_minutes=rate_info.secondary_window_minutes,
                    secondary_reset_at=datetime.fromtimestamp(
                        rate_info.secondary_reset_at
                    )
                    if rate_info.secondary_reset_at
                    else None,
                )

        except httpx.RequestError as e:
            logger.error(f"Network error: {e}")
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=True,
                account_id=account_info.get("account_id"),
                email=account_info.get("email"),
                error=f"Network error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"API error: {e}")
            return UsageLimits(
                provider=self.PROVIDER_NAME,
                is_authenticated=True,
                account_id=account_info.get("account_id"),
                email=account_info.get("email"),
                error=f"API error: {str(e)}",
            )

    def is_authenticated(self) -> bool:
        return self.oauth.is_authenticated()

    def get_auth_url(self, add_new_account: bool = False) -> str:
        flow = self.oauth.create_authorization_flow(add_new_account=add_new_account)
        return flow.url

    async def handle_callback(self, code: str, state: str) -> bool:
        tokens = await self.oauth.exchange_code(code, state)
        return tokens is not None

    def logout(self) -> bool:
        return self.oauth.logout()
