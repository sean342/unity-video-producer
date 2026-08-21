"""Persistent server-side media library for configurable Unity video intros and outros."""
from __future__ import annotations

import json
import mimetypes
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "media_library.db"
MEDIA_DIR = BASE_DIR / "assets" / "media_library"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
RATIOS = {"all", "1:1", "4:5", "9:16", "16:9"}
SLOTS = {"intro", "outro"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS media_assets (
            id TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL CHECK(media_type IN ('image','video','audio')),
            mime_type TEXT NOT NULL,
            duration_seconds REAL,
            has_audio INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS media_assignments (
            slot TEXT NOT NULL CHECK(slot IN ('intro','outro')),
            output_ratio TEXT NOT NULL,
            scene_asset_id TEXT NOT NULL,
            audio_asset_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(slot, output_ratio),
            FOREIGN KEY(scene_asset_id) REFERENCES media_assets(id) ON DELETE CASCADE,
            FOREIGN KEY(audio_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL
        )"""
    )
    return conn


def _probe(path: Path) -> tuple[Optional[float], bool]:
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20)
        data = json.loads(result.stdout)
        duration_value = data.get("format", {}).get("duration")
        duration = float(duration_value) if duration_value else None
        has_audio = any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))
        return duration, has_audio
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return None, False


def classify_upload(filename: str, mime_type: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image", mime_type or mimetypes.guess_type(filename)[0] or "image/*"
    if suffix in VIDEO_EXTENSIONS:
        return "video", mime_type or mimetypes.guess_type(filename)[0] or "video/*"
    if suffix in AUDIO_EXTENSIONS:
        return "audio", mime_type or mimetypes.guess_type(filename)[0] or "audio/*"
    raise ValueError("Use a JPG, PNG, WebP, MP4, MOV, WebM, MP3, WAV, M4A, AAC, or OGG file.")


def initialize_media_library() -> None:
    """Initialize persistent storage and register the existing vertical outro as a managed default."""
    with _lock:
        conn = _connect()
        try:
            existing = conn.execute("SELECT scene_asset_id FROM media_assignments WHERE slot='outro' AND output_ratio='9:16'").fetchone()
            legacy_outro = BASE_DIR / "assets" / "unified_vertical_outro.mp4"
            if not existing and legacy_outro.exists():
                stored_name = "unified_vertical_outro.mp4"
                library_path = MEDIA_DIR / stored_name
                if not library_path.exists():
                    library_path.write_bytes(legacy_outro.read_bytes())
                asset = conn.execute("SELECT id FROM media_assets WHERE stored_name=?", (stored_name,)).fetchone()
                if asset:
                    asset_id = asset["id"]
                else:
                    duration, has_audio = _probe(library_path)
                    asset_id = f"asset_{uuid.uuid4().hex}"
                    conn.execute(
                        """INSERT INTO media_assets(id, original_name, stored_name, media_type, mime_type, duration_seconds, has_audio, created_at)
                           VALUES (?, ?, ?, 'video', 'video/mp4', ?, ?, ?)""",
                        (asset_id, "Unified vertical outro", stored_name, duration, int(has_audio), _now()),
                    )
                conn.execute(
                    """INSERT OR REPLACE INTO media_assignments(slot, output_ratio, scene_asset_id, audio_asset_id, updated_at)
                       VALUES ('outro', '9:16', ?, NULL, ?)""",
                    (asset_id, _now()),
                )
            conn.commit()
        finally:
            conn.close()
        try:
            DB_PATH.chmod(0o600)
            MEDIA_DIR.chmod(0o700)
        except OSError:
            pass


def save_upload(filename: str, mime_type: str, content: bytes) -> dict:
    if not filename:
        raise ValueError("A file is required.")
    if not content:
        raise ValueError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploads must be 100 MB or smaller.")
    media_type, normalized_mime = classify_upload(filename, mime_type)
    suffix = Path(filename).suffix.lower()
    asset_id = f"asset_{uuid.uuid4().hex}"
    stored_name = f"{asset_id}{suffix}"
    destination = MEDIA_DIR / stored_name
    with _lock:
        conn = _connect()
        try:
            destination.write_bytes(content)
            duration, has_audio = _probe(destination) if media_type in {"video", "audio"} else (None, False)
            conn.execute(
                """INSERT INTO media_assets(id, original_name, stored_name, media_type, mime_type, duration_seconds, has_audio, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, Path(filename).name, stored_name, media_type, normalized_mime, duration, int(has_audio), _now()),
            )
            conn.commit()
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            conn.close()
    return get_asset(asset_id) or {}


def _asset_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["original_name"],
        "media_type": row["media_type"],
        "mime_type": row["mime_type"],
        "duration_seconds": row["duration_seconds"],
        "has_audio": bool(row["has_audio"]),
        "created_at": row["created_at"],
        "url": f"/settings/media/files/{row['id']}",
    }


def list_assets() -> list[dict]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM media_assets ORDER BY created_at DESC").fetchall()
        finally:
            conn.close()
    return [_asset_dict(row) for row in rows]


def get_asset(asset_id: str) -> Optional[dict]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM media_assets WHERE id=?", (asset_id,)).fetchone()
        finally:
            conn.close()
    return _asset_dict(row) if row else None


def get_asset_path(asset_id: str) -> Optional[Path]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT stored_name FROM media_assets WHERE id=?", (asset_id,)).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    path = MEDIA_DIR / row["stored_name"]
    return path if path.exists() else None


def delete_asset(asset_id: str) -> bool:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT stored_name FROM media_assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM media_assets WHERE id=?", (asset_id,))
            conn.commit()
        finally:
            conn.close()
    (MEDIA_DIR / row["stored_name"]).unlink(missing_ok=True)
    return True


def list_assignments() -> list[dict]:
    query = """
        SELECT a.slot, a.output_ratio, a.updated_at,
               s.id AS scene_id, s.original_name AS scene_name, s.media_type AS scene_type,
               s.duration_seconds AS scene_duration, s.has_audio AS scene_has_audio,
               au.id AS audio_id, au.original_name AS audio_name, au.duration_seconds AS audio_duration
        FROM media_assignments a
        JOIN media_assets s ON s.id = a.scene_asset_id
        LEFT JOIN media_assets au ON au.id = a.audio_asset_id
        ORDER BY a.slot, a.output_ratio
    """
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(query).fetchall()
        finally:
            conn.close()
    return [
        {
            "slot": row["slot"], "output_ratio": row["output_ratio"], "updated_at": row["updated_at"],
            "scene_asset_id": row["scene_id"], "scene_name": row["scene_name"],
            "scene_type": row["scene_type"], "scene_duration_seconds": row["scene_duration"],
            "scene_has_audio": bool(row["scene_has_audio"]), "audio_asset_id": row["audio_id"],
            "audio_name": row["audio_name"], "audio_duration_seconds": row["audio_duration"],
        }
        for row in rows
    ]


def save_assignment(slot: str, output_ratio: str, scene_asset_id: str, audio_asset_id: Optional[str]) -> dict:
    if slot not in SLOTS or output_ratio not in RATIOS:
        raise ValueError("Unsupported placement or output ratio.")
    scene = get_asset(scene_asset_id)
    if not scene or scene["media_type"] not in {"image", "video"}:
        raise ValueError("Choose an uploaded image or video scene.")
    if audio_asset_id:
        audio = get_asset(audio_asset_id)
        if not audio or audio["media_type"] != "audio":
            raise ValueError("Choose an uploaded audio file for background audio.")
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO media_assignments(slot, output_ratio, scene_asset_id, audio_asset_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(slot, output_ratio) DO UPDATE SET
                     scene_asset_id=excluded.scene_asset_id,
                     audio_asset_id=excluded.audio_asset_id,
                     updated_at=excluded.updated_at""",
                (slot, output_ratio, scene_asset_id, audio_asset_id or None, _now()),
            )
            conn.commit()
        finally:
            conn.close()
    return next(item for item in list_assignments() if item["slot"] == slot and item["output_ratio"] == output_ratio)


def clear_assignment(slot: str, output_ratio: str) -> None:
    if slot not in SLOTS or output_ratio not in RATIOS:
        raise ValueError("Unsupported placement or output ratio.")
    with _lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM media_assignments WHERE slot=? AND output_ratio=?", (slot, output_ratio))
            conn.commit()
        finally:
            conn.close()


def get_assignment(slot: str, output_ratio: str) -> Optional[dict]:
    requested = output_ratio if output_ratio in RATIOS else "9:16"
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT slot, output_ratio, scene_asset_id, audio_asset_id FROM media_assignments WHERE slot=? AND output_ratio IN (?, 'all') ORDER BY CASE output_ratio WHEN ? THEN 0 ELSE 1 END LIMIT 1",
                (slot, requested, requested),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    scene = get_asset(row["scene_asset_id"])
    audio = get_asset(row["audio_asset_id"]) if row["audio_asset_id"] else None
    if not scene:
        return None
    return {"slot": row["slot"], "output_ratio": row["output_ratio"], "scene": scene, "audio": audio}
