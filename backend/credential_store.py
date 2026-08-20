"""Encrypted, server-side credential storage for Unity Video Producer."""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "credentials.db"

PROVIDERS: Dict[str, Dict[str, str]] = {
    "openai": {"label": "OpenAI", "env": "OPENAI_API_KEY"},
    "elevenlabs": {"label": "ElevenLabs", "env": "ELEVENLABS_API_KEY"},
    "fal": {"label": "fal.ai / Kling", "env": "FAL_KEY"},
}

_lock = threading.RLock()


def _cipher() -> Fernet:
    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode("ascii"))


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS credentials (
            provider TEXT PRIMARY KEY,
            encrypted_value BLOB NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    return conn


def initialize_store() -> None:
    """Create the store and encrypt any existing server-only environment credentials once."""
    with _lock:
        conn = _connect()
        try:
            for provider, metadata in PROVIDERS.items():
                existing = conn.execute(
                    "SELECT 1 FROM credentials WHERE provider = ?", (provider,)
                ).fetchone()
                legacy_value = os.environ.get(metadata["env"], "").strip()
                if not existing and legacy_value:
                    encrypted = _cipher().encrypt(legacy_value.encode("utf-8"))
                    conn.execute(
                        "INSERT INTO credentials(provider, encrypted_value, updated_at) VALUES (?, ?, ?)",
                        (provider, encrypted, datetime.now(timezone.utc).isoformat()),
                    )
            conn.commit()
        finally:
            conn.close()
        try:
            DB_PATH.chmod(0o600)
        except OSError:
            pass


def get_credential(provider: str) -> str:
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unsupported credential provider: {provider}")
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT encrypted_value FROM credentials WHERE provider = ?", (provider,)
            ).fetchone()
        finally:
            conn.close()
    if row:
        try:
            return _cipher().decrypt(row[0]).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Credential store cannot decrypt this provider key") from exc
    return os.environ.get(PROVIDERS[provider]["env"], "").strip()


def credential_statuses() -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = {
                provider: updated_at
                for provider, updated_at in conn.execute(
                    "SELECT provider, updated_at FROM credentials"
                ).fetchall()
            }
        finally:
            conn.close()
    return [
        {
            "provider": provider,
            "label": metadata["label"],
            "configured": provider in rows or bool(os.environ.get(metadata["env"], "").strip()),
            "storage": "encrypted" if provider in rows else "legacy environment",
            "updated_at": rows.get(provider),
        }
        for provider, metadata in PROVIDERS.items()
    ]


def validate_credential(provider: str, value: str) -> Tuple[bool, str]:
    """Validate only with lightweight provider APIs; never log or return key material."""
    value = value.strip()
    if not value:
        return False, "A key is required."
    try:
        if provider == "openai":
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {value}"},
                timeout=12,
            )
        elif provider == "elevenlabs":
            response = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": value},
                timeout=12,
            )
        elif provider == "fal":
            response = requests.get(
                "https://api.fal.ai/v1/models?limit=1",
                headers={"Authorization": f"Key {value}"},
                timeout=12,
            )
            if response.status_code == 200:
                response = requests.post(
                    "https://rest.fal.ai/storage/auth/token?storage_type=fal-cdn-v3",
                    headers={"Authorization": f"Key {value}"},
                    json={},
                    timeout=12,
                )
        else:
            return False, "Unsupported provider."
    except requests.RequestException:
        return False, "Could not reach the provider to validate this key."

    if response.status_code == 200:
        return True, "Validated successfully."
    if provider == "fal" and response.status_code == 403:
        return False, "fal.ai rejected CDN storage access. Use a key with the required workspace permissions."
    if response.status_code in (401, 403):
        return False, "The provider rejected this key or its permissions."
    return False, "The provider could not validate this key right now."


def store_credential(provider: str, value: str) -> Tuple[bool, str]:
    if provider not in PROVIDERS:
        return False, "Unsupported provider."
    valid, message = validate_credential(provider, value)
    if not valid:
        return False, message
    encrypted = _cipher().encrypt(value.strip().encode("utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO credentials(provider, encrypted_value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(provider) DO UPDATE SET
                     encrypted_value = excluded.encrypted_value,
                     updated_at = excluded.updated_at""",
                (provider, encrypted, now),
            )
            conn.commit()
        finally:
            conn.close()
    return True, "Validated and encrypted on the server."
