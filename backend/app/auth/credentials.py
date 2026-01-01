"""Secure token storage using encrypted local file with multi-account support."""

import json
import os
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional, List, Dict
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from ..config import ACCOUNT_ID_LENGTH

logger = logging.getLogger(__name__)


class CredentialManager:
    """Manages secure storage of OAuth tokens with multi-account support."""
    
    STORAGE_DIR = Path.home() / ".aicap"
    TOKENS_FILE = STORAGE_DIR / "tokens.enc"
    SALT_FILE = STORAGE_DIR / ".salt"
    PBKDF2_ITERATIONS = 480000
    
    @classmethod
    def _ensure_storage_dir(cls) -> None:
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cls.STORAGE_DIR, 0o700)
        except Exception:
            pass
    
    @classmethod
    def _get_machine_secret(cls) -> bytes:
        components = [
            os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERNAME", ""),
            os.environ.get("USERDOMAIN", ""),
            str(Path.home()),
        ]
        combined = "|".join(components).encode("utf-8")
        return hashlib.sha256(combined).digest()
    
    @classmethod
    def _get_or_create_salt(cls) -> bytes:
        cls._ensure_storage_dir()
        if cls.SALT_FILE.exists():
            return cls.SALT_FILE.read_bytes()
        salt = os.urandom(32)
        cls.SALT_FILE.write_bytes(salt)
        try:
            os.chmod(cls.SALT_FILE, 0o600)
        except Exception:
            pass
        return salt

    @classmethod
    def _derive_key(cls) -> bytes:
        salt = cls._get_or_create_salt()
        machine_secret = cls._get_machine_secret()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=cls.PBKDF2_ITERATIONS,
        )
        key = kdf.derive(machine_secret)
        return base64.urlsafe_b64encode(key)
    
    @classmethod
    def _get_fernet(cls) -> Fernet:
        key = cls._derive_key()
        return Fernet(key)

    @classmethod
    def _load_all_data(cls) -> dict:
        """Load all data from encrypted file."""
        if not cls.TOKENS_FILE.exists():
            return {"accounts": {}, "active_account": None}
        try:
            fernet = cls._get_fernet()
            encrypted = cls.TOKENS_FILE.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            # Migration: convert old format to new
            if "accounts" not in data:
                if "openai" in data:
                    account_id = str(uuid.uuid4())[:8]
                    return {
                        "accounts": {account_id: {"provider": "openai", "tokens": data["openai"], "name": "Account 1"}},
                        "active_account": account_id
                    }
                return {"accounts": {}, "active_account": None}
            return data
        except (InvalidToken, json.JSONDecodeError) as e:
            logger.error(f"Failed to load data: {e}")
            return {"accounts": {}, "active_account": None}
    
    @classmethod
    def _save_all_data(cls, data: dict) -> bool:
        try:
            cls._ensure_storage_dir()
            fernet = cls._get_fernet()
            encrypted = fernet.encrypt(json.dumps(data).encode("utf-8"))
            cls.TOKENS_FILE.write_bytes(encrypted)
            try:
                os.chmod(cls.TOKENS_FILE, 0o600)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            return False

    # ===== Multi-Account Methods =====
    
    @classmethod
    def create_account(cls, provider: str, tokens: dict, name: Optional[str] = None) -> str:
        """Create new account and return its ID."""
        data = cls._load_all_data()
        account_id = str(uuid.uuid4())[:ACCOUNT_ID_LENGTH]
        account_num = len(data["accounts"]) + 1
        data["accounts"][account_id] = {
            "provider": provider,
            "tokens": tokens,
            "name": name or f"Account {account_num}"
        }
        if data["active_account"] is None:
            data["active_account"] = account_id
        cls._save_all_data(data)
        logger.info(f"Created account {account_id}")
        return account_id
    
    @classmethod
    def get_accounts(cls, provider: Optional[str] = None) -> List[Dict]:
        """Get all accounts, optionally filtered by provider."""
        data = cls._load_all_data()
        accounts = []
        for acc_id, acc_data in data["accounts"].items():
            if provider is None or acc_data.get("provider") == provider:
                accounts.append({
                    "id": acc_id,
                    "provider": acc_data.get("provider"),
                    "name": acc_data.get("name", "Unnamed"),
                    "is_active": acc_id == data["active_account"]
                })
        return accounts
    
    @classmethod
    def get_account(cls, account_id: str) -> Optional[Dict]:
        """Get account by ID."""
        data = cls._load_all_data()
        acc = data["accounts"].get(account_id)
        if acc:
            return {
                "id": account_id,
                "provider": acc.get("provider"),
                "name": acc.get("name"),
                "tokens": acc.get("tokens"),
                "is_active": account_id == data["active_account"]
            }
        return None
    
    @classmethod
    def get_active_account(cls, provider: str) -> Optional[Dict]:
        """Get active account for provider."""
        data = cls._load_all_data()
        active_id = data.get("active_account")
        if active_id and active_id in data["accounts"]:
            acc = data["accounts"][active_id]
            if acc.get("provider") == provider:
                return {"id": active_id, **acc}
        # Fallback: return first account for provider
        for acc_id, acc in data["accounts"].items():
            if acc.get("provider") == provider:
                return {"id": acc_id, **acc}
        return None

    @classmethod
    def set_active_account(cls, account_id: str) -> bool:
        """Set active account."""
        data = cls._load_all_data()
        if account_id in data["accounts"]:
            data["active_account"] = account_id
            return cls._save_all_data(data)
        return False
    
    @classmethod
    def update_account_name(cls, account_id: str, name: str) -> bool:
        """Update account name."""
        data = cls._load_all_data()
        if account_id in data["accounts"]:
            data["accounts"][account_id]["name"] = name
            return cls._save_all_data(data)
        return False
    
    @classmethod
    def update_account_tokens(cls, account_id: str, tokens: dict) -> bool:
        """Update tokens for account."""
        data = cls._load_all_data()
        if account_id in data["accounts"]:
            data["accounts"][account_id]["tokens"] = tokens
            return cls._save_all_data(data)
        return False
    
    @classmethod
    def delete_account(cls, account_id: str) -> bool:
        """Delete account."""
        data = cls._load_all_data()
        if account_id in data["accounts"]:
            del data["accounts"][account_id]
            if data["active_account"] == account_id:
                # Set new active account
                data["active_account"] = next(iter(data["accounts"]), None)
            return cls._save_all_data(data)
        return False
    
    # ===== Legacy compatibility methods =====
    
    @classmethod
    def save_tokens(cls, provider: str, tokens: dict) -> bool:
        """Legacy: Save tokens (creates or updates active account)."""
        active = cls.get_active_account(provider)
        if active:
            return cls.update_account_tokens(active["id"], tokens)
        cls.create_account(provider, tokens)
        return True
    
    @classmethod
    def get_tokens(cls, provider: str) -> Optional[dict]:
        """Legacy: Get tokens for active account."""
        active = cls.get_active_account(provider)
        return active.get("tokens") if active else None
    
    @classmethod
    def delete_tokens(cls, provider: str) -> bool:
        """Legacy: Delete active account."""
        active = cls.get_active_account(provider)
        if active:
            return cls.delete_account(active["id"])
        return True
    
    @classmethod
    def has_tokens(cls, provider: str) -> bool:
        """Legacy: Check if any account exists."""
        return cls.get_active_account(provider) is not None
