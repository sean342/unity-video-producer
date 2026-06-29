"""
Shared keyframe registry — allows pipeline modules to register newly generated
keyframes into main.py's KEYFRAME_META at runtime so they appear in the library
and keyframe picker immediately without a service restart.
"""
import logging

logger = logging.getLogger(__name__)

# This will be set by main.py on startup
_KEYFRAME_META: dict = {}


def set_registry(meta: dict):
    """Called by main.py to share its KEYFRAME_META dict reference."""
    global _KEYFRAME_META
    _KEYFRAME_META = meta


def register_keyframe(filename: str, label: str, tags: list[str]):
    """Register a newly generated keyframe into the shared KEYFRAME_META."""
    if filename not in _KEYFRAME_META:
        _KEYFRAME_META[filename] = {"label": label, "tags": tags}
        logger.info(f"[keyframe_registry] Registered new keyframe: {filename} ({label})")
    else:
        logger.debug(f"[keyframe_registry] Keyframe already registered: {filename}")
