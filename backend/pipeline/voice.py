"""
Voice generation — ElevenLabs with per-client voice ID and settings.
Voice config is loaded from clients.json via client_config.
"""
import os
import json
import base64
import requests
from pathlib import Path
from typing import Tuple, Dict

from .client_config import get_client

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")


def generate_voice(script: str, job_dir: Path, client_id: str = "unified") -> Tuple[Path, Dict]:
    """
    Generate voiceover with word-level timestamps using client-specific voice.
    Returns (mp3_path, alignment_dict).
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    client = get_client(client_id)
    voice_id = client["voice_id"]
    voice_settings = client["voice_settings"]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": voice_settings,
    }
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs failed ({r.status_code}): {r.text[:300]}")

    data = r.json()

    # Save audio
    audio_bytes = base64.b64decode(data["audio_base64"])
    audio_path = job_dir / "voice.mp3"
    audio_path.write_bytes(audio_bytes)

    # Save timestamps
    alignment = data["alignment"]
    ts_path = job_dir / "timestamps.json"
    ts_path.write_text(json.dumps(alignment, indent=2))

    return audio_path, alignment
