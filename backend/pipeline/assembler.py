"""
Video assembler — FFmpeg with caption overlays, Unified logo, BGM, and optional comedy SFX.
- Logo: bottom-left, x=30, 35px from bottom
- BGM: 10% volume
- Captions: timed PNG overlays above logo
- Comedy: laugh/applause clips mixed in at GPT-specified cue offsets
- Output: libx264 fast CRF 18, AAC 192k, faststart
"""
import subprocess
import os
from pathlib import Path
from typing import List, Dict, Optional

from .client_config import get_asset_path

ASSETS_DIR = Path(__file__).parent.parent / "assets"

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
    comedy_cues: Optional[List] = None,
    client_id: str = "unified",
) -> Path:
    """
    Assemble final video with logo, captions, BGM, and optional comedy audience SFX.

    comedy_cues: list of AudienceCue objects with:
        - offset_seconds: when to start the clip (relative to video start)
        - reaction_type: "laugh" or "applause"
        - duration_seconds: how long to play (clip will be trimmed/faded)

    Returns path to final MP4.
    """
    # Load client-specific assets
    LOGO_SRC = get_asset_path(client_id, "logo")
    BGM_SRC = get_asset_path(client_id, "bgm")
    LAUGH_SRC = get_asset_path(client_id, "comedy_laugh")
    APPLAUSE_SRC = get_asset_path(client_id, "comedy_applause")

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

    # ── Build input list ────────────────────────────────────────────────────
    # [0] raw video (has embedded voice audio from Kling)
    # [1] logo
    # [2] BGM
    # [3..N] caption PNGs
    # [N+1..] comedy SFX clips (if any)

    inputs = ["-i", str(raw_video), "-i", str(logo_small), "-i", str(BGM_SRC)]
    for cap in captions:
        inputs += ["-i", cap["png"]]

    # Prepare comedy SFX inputs
    comedy_audio_inputs = []  # list of (input_index, offset_seconds, duration_seconds)
    if comedy_cues:
        for cue in comedy_cues:
            offset = getattr(cue, "offset_seconds", -1)
            if offset < 0:
                continue  # skip unresolved cues
            reaction = getattr(cue, "reaction_type", "laugh")
            duration = getattr(cue, "duration_seconds", 2.5)
            sfx_path = LAUGH_SRC if reaction == "laugh" else APPLAUSE_SRC
            if not sfx_path.exists():
                print(f"[assembler] Warning: SFX file not found: {sfx_path}")
                continue
            idx = 3 + len(captions) + len(comedy_audio_inputs)
            inputs += ["-i", str(sfx_path)]
            comedy_audio_inputs.append((idx, offset, duration))
            print(f"[assembler] Comedy SFX: {reaction} at {offset:.2f}s (input [{idx}])")

    # ── Build filter_complex ────────────────────────────────────────────────
    filter_parts = []

    # Video: logo overlay
    filter_parts.append(f"[0:v][1:v]overlay=x={logo_x}:y={logo_y}[v0]")
    prev = "v0"

    # Video: caption overlays
    for i, cap in enumerate(captions):
        inp_idx = i + 3
        cap_y = VH - cap["height"] - lh - 55
        next_v = f"v{i + 1}"
        enable = f"between(t\\,{cap['start']:.3f}\\,{cap['end']:.3f})"
        filter_parts.append(
            f"[{prev}][{inp_idx}:v]overlay=x=0:y={cap_y}:enable='{enable}'[{next_v}]"
        )
        prev = next_v

    # Audio: BGM at 10%
    filter_parts.append("[2:a]volume=0.10[bgm]")

    # Audio: comedy SFX — each clip delayed to its cue offset, trimmed, faded out
    sfx_labels = []
    for i, (inp_idx, offset, duration) in enumerate(comedy_audio_inputs):
        label = f"sfx{i}"
        # Trim to duration, apply short fade-out, then delay to offset
        filter_parts.append(
            f"[{inp_idx}:a]atrim=duration={duration:.2f},"
            f"afade=t=out:st={max(0, duration - 0.4):.2f}:d=0.4,"
            f"adelay={int(offset * 1000)}|{int(offset * 1000)},"
            f"volume=0.75[{label}]"
        )
        sfx_labels.append(f"[{label}]")

    # Audio: mix everything — voice + BGM + all SFX
    all_audio_count = 2 + len(sfx_labels)  # voice + bgm + sfx clips
    if sfx_labels:
        sfx_chain = "".join(sfx_labels)
        # Build weights: voice=1, bgm=0.10, each sfx=0.75
        weights = "1 0.10" + " 0.75" * len(sfx_labels)
        filter_parts.append(
            f"[0:a][bgm]{sfx_chain}amix=inputs={all_audio_count}:duration=longest:weights={weights}[aout]"
        )
    else:
        filter_parts.append(
            f"[0:a][bgm]amix=inputs=2:duration=first:weights=1 0.10[aout]"
        )

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
    print(f"[assembler] Output: {output_path.name} ({size_mb:.1f} MB)")
    return output_path
