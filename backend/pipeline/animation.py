"""
Animation — Kling Avatar v2 via fal.ai.
Generates lip-synced animated video from keyframe + voice audio.
"""
import os
import time
import subprocess
import requests
from pathlib import Path

FAL_KEY = os.environ.get("FAL_KEY", "efc35cb5-2721-4551-927a-9e551b153bb2:da72a3ac272f43067486b6bd43d05929")

KLING_ENDPOINT = "https://queue.fal.run/fal-ai/kling-video/ai-avatar/v2/pro"
KLING_STATUS_BASE = "https://queue.fal.run/fal-ai/kling-video/requests"

SCENE_ACTIONS = {
    "doors":      "standing next to a door, gesturing and speaking to camera",
    "windows":    "standing next to a window, gesturing and speaking to camera",
    "roofing":    "standing on a rooftop, pointing upward and speaking to camera",
    "siding":     "standing in front of a house, gesturing at the wall and speaking",
    "insulation": "standing in an attic, gesturing around and speaking to camera",
    "gutters":    "standing near gutters, pointing and speaking to camera",
    "default":    "standing in a home interior, speaking directly to camera",
}


def get_action(topic: str) -> str:
    topic_lower = topic.lower()
    for key, action in SCENE_ACTIONS.items():
        if key in topic_lower:
            return action
    return SCENE_ACTIONS["default"]


def generate_animation(
    keyframe_url: str,
    voice_path: Path,
    topic: str,
    job_dir: Path,
) -> Path:
    """
    Submit Kling Avatar v2 job, poll until complete, download raw video.
    Returns path to downloaded raw MP4.
    """
    # Upload voice audio to CDN
    audio_url = _upload_to_cdn(voice_path)

    action = get_action(topic)
    prompt = (
        f"Unity the golden retriever mascot {action}. "
        f"Smooth 3D animation. Fluffy golden tail clearly visible and wagging. "
        f"Natural body movement and gestures. Mouth moves naturally with speech. "
        f"Red bandana with house icon. Brown tool belt with wrench and hammer. "
        f"Friendly energetic expression."
    )
    negative_prompt = (
        "missing tail, no tail, human hands, distorted legs, floating, blurry, "
        "text signs on wall, extra limbs, deformed"
    )

    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "image_url": keyframe_url,
        "audio_url": audio_url,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }

    # Submit job
    r = requests.post(KLING_ENDPOINT, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Kling submission failed ({r.status_code}): {r.text[:300]}")

    data = r.json()
    request_id = data.get("request_id")
    if not request_id:
        raise RuntimeError(f"No request_id in Kling response: {data}")

    status_url = f"{KLING_STATUS_BASE}/{request_id}/status"
    result_url = f"{KLING_STATUS_BASE}/{request_id}"

    # Poll for completion (max 10 min)
    for attempt in range(75):
        time.sleep(8)
        sr = requests.get(status_url, headers=headers, timeout=15)
        sd = sr.json()
        status = sd.get("status", "unknown")
        if attempt % 5 == 0:
            pass  # progress logged by orchestrator
        if status == "COMPLETED":
            break
        elif status in ("FAILED", "ERROR"):
            raise RuntimeError(f"Kling job failed: {sd}")

    # Get result
    rr = requests.get(result_url, headers=headers, timeout=15)
    rd = rr.json()
    video_url = (
        rd.get("video", {}).get("url")
        or (rd.get("videos") or [{}])[0].get("url")
    )
    if not video_url:
        raise RuntimeError(f"No video URL in Kling result: {rd}")

    # Download raw video
    vr = requests.get(video_url, timeout=120)
    raw_path = job_dir / "kling_raw.mp4"
    raw_path.write_bytes(vr.content)
    return raw_path


def _upload_to_cdn(local_path: Path) -> str:
    """Upload local file to Manus CDN and return URL."""
    result = subprocess.run(
        ["manus-upload-file", str(local_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Upload failed: {result.stderr}")
    lines = result.stdout.strip().split("\n")
    for line in reversed(lines):
        if line.startswith("http"):
            return line.strip()
    raise RuntimeError(f"Could not parse CDN URL from: {result.stdout}")
