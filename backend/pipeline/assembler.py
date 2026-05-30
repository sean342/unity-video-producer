"""
Video assembler — FFmpeg with caption overlays, Unified logo, and BGM.
- Logo: bottom-left, x=30, 35px from bottom
- BGM: 10% volume
- Captions: timed PNG overlays above logo
- Output: libx264 fast CRF 18, AAC 192k, faststart
"""
import subprocess
import os
from pathlib import Path
from typing import List, Dict

ASSETS_DIR = Path(__file__).parent.parent / "assets"
LOGO_SRC = ASSETS_DIR / "templates" / "unified_logo.png"
BGM_SRC = ASSETS_DIR / "templates" / "bgm.mp3"

VW, VH = 1072, 1920


def _get_logo_dimensions(logo_path: Path) -> tuple:
    """Get logo dimensions via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(logo_path),
        ],
        capture_output=True,
        text=True,
    )
    parts = result.stdout.strip().split(",")
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    return 200, 80  # fallback


def assemble_video(
    raw_video: Path,
    captions: List[Dict],
    output_path: Path,
) -> Path:
    """
    Assemble final video with logo, captions, and BGM.
    Returns path to final MP4.
    """
    # Resize logo to 200px wide
    logo_small = raw_video.parent / "logo_small.png"
    if not logo_small.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(LOGO_SRC), "-vf", "scale=200:-1", str(logo_small)],
            capture_output=True,
            check=True,
        )

    lw, lh = _get_logo_dimensions(logo_small)
    logo_x = 30
    logo_y = VH - lh - 35

    # Build FFmpeg inputs
    inputs = ["-i", str(raw_video), "-i", str(logo_small), "-i", str(BGM_SRC)]
    for cap in captions:
        inputs += ["-i", cap["png"]]

    # Build filter_complex
    filter_parts = []
    filter_parts.append(f"[0:v][1:v]overlay=x={logo_x}:y={logo_y}[v0]")
    prev = "v0"

    for i, cap in enumerate(captions):
        inp_idx = i + 3
        cap_y = VH - cap["height"] - lh - 55
        next_v = f"v{i + 1}"
        enable = f"between(t\\,{cap['start']:.3f}\\,{cap['end']:.3f})"
        filter_parts.append(
            f"[{prev}][{inp_idx}:v]overlay=x=0:y={cap_y}:enable='{enable}'[{next_v}]"
        )
        prev = next_v

    filter_parts.append("[2:a]volume=0.10[bgm]")
    filter_parts.append(f"[0:a][bgm]amix=inputs=2:duration=first:weights=1 0.10[aout]")
    filter_complex = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", f"[{prev}]",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]
    )

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-2000:]}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    return output_path
