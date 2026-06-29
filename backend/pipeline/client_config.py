"""
Client configuration loader.
Reads clients.json and provides per-client settings to the pipeline.
All pipeline modules should import get_client() instead of hardcoding brand values.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CLIENTS_FILE = Path(__file__).parent.parent / "clients.json"
BACKEND_DIR = Path(__file__).parent.parent

_cache: dict = {}


def _load_clients() -> dict:
    global _cache
    if _cache:
        return _cache
    try:
        with open(CLIENTS_FILE) as f:
            _cache = json.load(f)
        logger.info(f"[client_config] Loaded {len(_cache)} client(s): {list(_cache.keys())}")
    except Exception as e:
        logger.error(f"[client_config] Failed to load clients.json: {e}")
        _cache = {}
    return _cache


def get_client(client_id: str = "unified") -> dict:
    """
    Return the full config dict for a client.
    Falls back to 'unified' if client_id not found.
    Raises ValueError if neither exists.
    """
    clients = _load_clients()
    if client_id in clients:
        return clients[client_id]
    if "unified" in clients:
        logger.warning(f"[client_config] Client '{client_id}' not found, falling back to 'unified'")
        return clients["unified"]
    raise ValueError(f"Client '{client_id}' not found and no fallback available")


def get_asset_path(client_id: str, asset_key: str) -> Optional[Path]:
    """
    Return the absolute Path for a client asset by key.
    e.g. get_asset_path("unified", "logo") -> Path("/opt/.../assets/templates/unified_logo.png")
    """
    client = get_client(client_id)
    rel = client.get("assets", {}).get(asset_key)
    if not rel:
        return None
    return BACKEND_DIR / rel


def list_clients() -> list:
    """Return list of all active client IDs."""
    clients = _load_clients()
    return [cid for cid, cfg in clients.items() if cfg.get("active", True)]


def reload_clients():
    """Force reload of clients.json (useful after edits)."""
    global _cache
    _cache = {}
    return _load_clients()
