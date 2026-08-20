"""
Voice animation — Kling AI Avatar v2 Pro via fal.ai.
Supports chunked animation for audio longer than 9 seconds:
  - Audio is split into evenly-distributed ≤9s segments using FFmpeg
  - Multi-angle mode: each chunk uses an _alt1 / _alt2 keyframe variant
    to simulate a camera angle cut between sections (preferred)
  - Fallback continuity mode: uses the LAST FRAME of the previous chunk
    as its keyframe so Unity's pose continues seamlessly between clips
  - Chunks are stitched into one seamless video
  - Minimum chunk duration enforced (≥2s) to avoid Kling rejection
"""
import os
import subprocess
import requests
from pathlib import Path
from credential_store import get_credential


FAL_KEY = os.environ.get("FAL_KEY", "")

# Kling Avatar v2 Pro max clip duration (seconds)
KLING_MAX_SECONDS = 9
# Minimum chunk duration — Kling rejects clips shorter than this
KLING_MIN_SECONDS = 2.0

# Client config loader (inline to avoid circular import)
def get_client(client_id: str = "unified") -> dict:
    import json
    clients_path = Path(__file__).parent.parent / "clients.json"
    if clients_path.exists():
        with open(clients_path) as f:
            clients = json.load(f)
        return clients.get(client_id, {})
    return {}

SCENE_ACTIONS = {
    "window":     "standing near a window, gesturing and speaking to camera",
    "door":       "standing near a front door, gesturing and speaking to camera",
    "roof":       "crouching on a rooftop, gesturing and speaking to camera",
    "siding":     "pointing at house siding, speaking to camera",
    "insulation": "in an attic with insulation, speaking to camera",
    "gutter":     "on a ladder near gutters, gesturing and speaking to camera",
    "bath":       "in a remodeled bathroom, speaking to camera",
    "sunroom":    "in a bright sunroom, speaking to camera",
    "energy":     "in front of an energy-efficient house, speaking to camera",
    "financing":  "standing beside a financing sign, speaking to camera with empty paws",
    "review":     "next to a 5-star review, speaking to camera",
    "teach":      "at a whiteboard, gesturing and speaking to camera",
    "comedy":     "at a comedy microphone, speaking to camera",
    "driving":    "in a company van, speaking to camera",
    "gutter":     "standing near gutters, pointing and speaking to camera",
    "default":    "standing in a home interior, speaking directly to camera",
}

KEYFRAMES_DIR = Path(__file__).parent.parent / "assets" / "keyframes"

def get_action(topic: str) -> str:
    topic_lower = topic.lower()
    for key, action in SCENE_ACTIONS.items():
        if key in topic_lower:
            return action
    return SCENE_ACTIONS["default"]

def get_audio_duration(audio_path: Path) -> float:
    """Return audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

def split_audio(audio_path: Path, job_dir: Path, max_duration: float = KLING_MAX_SECONDS) -> list:
    """
    Split audio into evenly-distributed chunks, each ≤ max_duration seconds.
    Uses even distribution to avoid tiny leftover chunks that Kling rejects.
    Returns list of chunk paths.
    """
    total = get_audio_duration(audio_path)
    if total <= max_duration:
        return [audio_path]

    # Calculate number of chunks needed and distribute evenly
    import math
    n_chunks = math.ceil(total / max_duration)
    chunk_duration = total / n_chunks  # evenly distributed

    chunks = []
    start = 0.0
    for idx in range(n_chunks):
        chunk_path = job_dir / f"audio_chunk_{idx:02d}.mp3"
        # Last chunk gets the remainder
        duration = chunk_duration if idx < n_chunks - 1 else (total - start)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ss", str(start), "-t", str(duration),
            "-acodec", "libmp3lame", "-q:a", "2",
            str(chunk_path)
        ], capture_output=True)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            actual_dur = get_audio_duration(chunk_path)
            if actual_dur >= KLING_MIN_SECONDS:
                chunks.append(chunk_path)
            else:
                # Chunk too short — merge into previous by removing it
                # (the previous chunk will just run a little longer in the stitch)
                chunk_path.unlink(missing_ok=True)
        start += chunk_duration

    return chunks if chunks else [audio_path]

def upload_to_cdn(local_path: Path, mime_type: str = "image/png") -> str:
    """Upload a file to fal.ai CDN and return a public URL."""
    import fal_client
    fal_key = get_credential("fal")
    client = fal_client.SyncClient(key=fal_key)
    url = client.upload_file(local_path)
    return url

def extract_last_frame(video_path: Path, output_path: Path) -> Path:
    """
    Extract the very last frame of a video as a PNG.
    Used as the keyframe for the next chunk so Unity's pose continues seamlessly.
    """
    # Get duration
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        duration = 5.0

    # Extract frame 0.1s before the end to avoid black frames
    seek_time = max(0.0, duration - 0.1)
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(seek_time),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_path)
    ], capture_output=True, check=True)
    return output_path

def get_alt_keyframe_sequence(base_keyframe_path: Path) -> list:
    """
    Given a base keyframe path (e.g., windows.png), return an ordered list
    of keyframe paths for multi-chunk animation:
      [windows.png, windows_alt1.png, windows_alt2.png, windows.png, ...]
    
    If alt variants don't exist, returns [base_keyframe_path] (single-angle mode).
    The sequence cycles: base → alt1 → alt2 → base → alt1 → ...
    """
    base_name = base_keyframe_path.stem  # e.g., "windows"
    base_dir = base_keyframe_path.parent
    
    alt1_path = base_dir / f"{base_name}_alt1.png"
    alt2_path = base_dir / f"{base_name}_alt2.png"
    
    sequence = [base_keyframe_path]
    if alt1_path.exists():
        sequence.append(alt1_path)
    if alt2_path.exists():
        sequence.append(alt2_path)
    
    return sequence

def animate_chunk(
    keyframe_url: str,
    audio_chunk_path: Path,
    prompt: str,
    chunk_index: int,
    job_dir: Path,
) -> Path:
    """Animate a single audio chunk with Kling. Returns path to downloaded chunk video."""
    import fal_client
    fal_key = get_credential("fal")
    os.environ["FAL_KEY"] = fal_key
    audio_url = upload_to_cdn(audio_chunk_path, "audio/mpeg")
    client = fal_client.SyncClient(key=fal_key)
    result = client.subscribe(
        "fal-ai/kling-video/ai-avatar/v2/pro",
        arguments={
            "image_url": keyframe_url,
            "audio_url": audio_url,
            "prompt": prompt,
        },
        with_logs=False,
    )
    video_url = result["video"]["url"]
    vr = requests.get(video_url, timeout=120)
    chunk_video_path = job_dir / f"kling_chunk_{chunk_index:02d}.mp4"
    chunk_video_path.write_bytes(vr.content)
    return chunk_video_path

def stitch_chunks(chunk_paths: list, job_dir: Path) -> Path:
    """Concatenate multiple video chunks into one seamless video using FFmpeg."""
    if len(chunk_paths) == 1:
        output = job_dir / "kling_raw.mp4"
        chunk_paths[0].rename(output)
        return output
    concat_list = job_dir / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in chunk_paths:
            f.write(f"file '{p.resolve()}'\n")
    output = job_dir / "kling_raw.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output)
    ], capture_output=True, check=True)
    return output

def generate_animation(
    keyframe_url: str,
    voice_path: Path,
    topic: str,
    job_dir: Path,
    client_id: str = "unified",
    keyframe_override: str = "",
) -> Path:
    """
    Animate Unity with Kling AI Avatar v2 Pro.
    
    Multi-angle mode (preferred when alt keyframes exist):
      - Chunk 0 uses the base keyframe
      - Chunk 1 uses _alt1 variant (different camera angle)
      - Chunk 2 uses _alt2 variant (another angle)
      - Chunk 3+ cycles back through the sequence
      - Creates natural camera cut transitions between sections
    
    Fallback continuity mode (when no alt keyframes exist):
      - Each subsequent chunk uses the last frame of the previous chunk
      - Unity's pose continues seamlessly between clips
    
    Returns path to the final raw MP4.
    """
    cfg = get_client(client_id)
    mascot_name = cfg.get("mascot_name", "the mascot")
    mascot_desc = cfg.get("mascot_description", "")
    action = get_action(topic)
    prompt = (
        f"{mascot_name} {action}. "
        f"Natural body movement and gestures using visibly empty paws. "
        f"{mascot_desc} "
        f"Do not add, remove, or morph any props during the clip. No handheld screwdriver, hammer, wrench, sign, microphone, tool, or object. "
        f"Friendly energetic expression."
    )

    # Split audio evenly
    audio_chunks = split_audio(voice_path, job_dir, KLING_MAX_SECONDS)

    if len(audio_chunks) == 1:
        # Single chunk — fast path, use original keyframe
        chunk_video = animate_chunk(keyframe_url, audio_chunks[0], prompt, 0, job_dir)
        output = job_dir / "kling_raw.mp4"
        if chunk_video != output:
            chunk_video.rename(output)
        return output

    # Multiple chunks — check if alt keyframes exist for multi-angle mode
    # Determine the base keyframe path from the override or topic-based selection
    base_keyframe_path = None
    if keyframe_override:
        candidate = KEYFRAMES_DIR / keyframe_override
        if candidate.exists():
            base_keyframe_path = candidate
    
    if base_keyframe_path is None:
        # Try to infer from topic keywords
        from pipeline.keyframe import select_keyframe_keyword
        base_keyframe_path = select_keyframe_keyword(topic, "")
    
    # Get the alt keyframe sequence for this base keyframe
    alt_sequence = []
    if base_keyframe_path and base_keyframe_path.exists():
        alt_sequence = get_alt_keyframe_sequence(base_keyframe_path)
    
    use_multiangle = len(alt_sequence) > 1
    
    if use_multiangle:
        print(f"[animation] Multi-angle mode: {len(alt_sequence)} angles for {len(audio_chunks)} chunks")
        # Upload all alt keyframes to CDN upfront
        alt_urls = []
        for alt_path in alt_sequence:
            try:
                url = upload_to_cdn(alt_path, "image/png")
                alt_urls.append(url)
                print(f"[animation] Uploaded alt keyframe: {alt_path.name}")
            except Exception as e:
                print(f"[animation] Warning: could not upload {alt_path.name}: {e}")
                alt_urls.append(keyframe_url)  # fallback to original
        
        chunk_videos = []
        for i, chunk_audio in enumerate(audio_chunks):
            # Cycle through alt sequence: 0→base, 1→alt1, 2→alt2, 3→base, ...
            angle_idx = i % len(alt_urls)
            current_keyframe_url = alt_urls[angle_idx]
            print(f"[animation] Chunk {i}: using angle {angle_idx} ({alt_sequence[angle_idx].name})")
            chunk_video = animate_chunk(current_keyframe_url, chunk_audio, prompt, i, job_dir)
            chunk_videos.append(chunk_video)
    else:
        # Fallback: continuity mode — use last frame of previous chunk as next keyframe
        print(f"[animation] Continuity mode: no alt keyframes found for this topic")
        chunk_videos = []
        current_keyframe_url = keyframe_url  # Start with the original keyframe

        for i, chunk_audio in enumerate(audio_chunks):
            chunk_video = animate_chunk(current_keyframe_url, chunk_audio, prompt, i, job_dir)
            chunk_videos.append(chunk_video)

            # Extract last frame of this chunk to use as keyframe for next chunk
            if i < len(audio_chunks) - 1:
                last_frame_path = job_dir / f"transition_frame_{i:02d}.png"
                try:
                    extract_last_frame(chunk_video, last_frame_path)
                    # Upload the transition frame to CDN
                    current_keyframe_url = upload_to_cdn(last_frame_path, "image/png")
                except Exception as e:
                    # If frame extraction fails, fall back to original keyframe
                    print(f"Warning: could not extract last frame from chunk {i}: {e}")
                    current_keyframe_url = keyframe_url

    return stitch_chunks(chunk_videos, job_dir)
