"""
Voice generation — ElevenLabs Unity v2 voice with word timestamps.
Voice ID: RlSomJYBsxja4xRQuPgO (Unity v2)
"""
import os
import json
import base64
import requests
from pathlib import Path
from typing import Tuple, Dict

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICE_ID = "RlSomJYBsxja4xRQuPgO"  # Unity v2 — locked

VOICE_SETTINGS = {
    "stability": 0.45,
    "similarity_boost": 0.78,
    "style": 0.35,
    "use_speaker_boost": True,
}


def generate_voice(script: str, job_dir: Path) -> Tuple[Path, Dict]:
    """
    Generate Unity v2 voiceover with word-level timestamps.
    Returns (mp3_path, alignment_dict).
    """
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": VOICE_SETTINGS,
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
