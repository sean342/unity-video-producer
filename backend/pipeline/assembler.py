"""
Video assembler — FFmpeg with caption overlays, Unified logo, BGM, optional comedy SFX,
and a five-second branded Unified Home Remodeling end screen.
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .client_config import get_asset_path
from .video_formats import get_video_format, normalized_output_ratio

ASSETS_DIR = Path(__file__).parent.parent / "assets"

VW, VH = 1072, 1920
END_SCREEN_DURATION_SECONDS = 5
UNIFIED_JINGLE_PATH = ASSETS_DIR / "unified_jingle.wav"
VERTICAL_OUTRO_PATH = ASSETS_DIR / "unified_vertical_outro.mp4"


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
    return 200, 80


def _get_media_duration_seconds(media_path: Path) -> float:
    """Return media duration in seconds for deterministic body render bounds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return 0.0


def _brand_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a dependable system font for rendered end-screen typography."""
    names = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


def _render_landscape_end_screen(client_id: str) -> Image.Image:
    """Render a dedicated 16:9 CTA composition with readable landscape hierarchy."""
    width, height = 1920, 1080
    background, charcoal, red, gold, white, muted = (14, 20, 34), (26, 29, 37), (196, 18, 48), (250, 166, 35), (250, 250, 250), (203, 211, 221)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 16), fill=red)
    draw.rectangle((0, height - 14, width, height), fill=gold)
    draw.polygon([(0, 0), (width, 0), (width, 300), (0, 510)], fill=(20, 31, 52))
    draw.polygon([(0, height), (width, height), (width, 820), (0, 980)], fill=charcoal)
    draw.rounded_rectangle((115, 52, width - 115, height - 52), radius=34, outline=(83, 93, 111), width=2)

    logo_path = get_asset_path(client_id, "logo")
    logo_bottom = 155
    if logo_path and Path(logo_path).exists():
        with Image.open(logo_path).convert("RGBA") as logo:
            logo.thumbnail((720, 190), Image.Resampling.LANCZOS)
            image.paste(logo, ((width - logo.width) // 2, 64), logo)
            logo_bottom = 64 + logo.height
    else:
        draw.text((width // 2, 120), "UNIFIED HOME REMODELING", font=_brand_font(62, bold=True), fill=white, anchor="mm")

    divider_y = logo_bottom + 36
    draw.line((420, divider_y, width - 420, divider_y), fill=gold, width=4)
    draw.multiline_text((width // 2, divider_y + 112), "Schedule Your FREE\nConsultation Today", font=_brand_font(72, bold=True), fill=white, anchor="mm", align="center", spacing=8)
    phone_top = divider_y + 236
    draw.rounded_rectangle((610, phone_top, width - 610, phone_top + 118), radius=30, fill=red)
    draw.text((width // 2, phone_top + 59), "☎  888-631-2131", font=_brand_font(54, bold=True), fill=white, anchor="mm")
    draw.text((width // 2, phone_top + 195), "◉  UnifiedHomeRemodeling.com", font=_brand_font(40, bold=True), fill=gold, anchor="mm")
    services_y = phone_top + 300
    draw.line((510, services_y, width - 510, services_y), fill=(83, 93, 111), width=2)
    draw.text((width // 2, services_y + 58), "Windows  •  Doors  •  Siding  •  Roofing  •  And More", font=_brand_font(34, bold=True), fill=muted, anchor="mm")
    badge_top = height - 170
    draw.rounded_rectangle((630, badge_top, width - 630, badge_top + 80), radius=40, outline=gold, width=3)
    draw.text((width // 2, badge_top + 40), "Family Owned & Operated Since 1989", font=_brand_font(30, bold=True), fill=white, anchor="mm")
    return image


def _render_end_screen(output_path: Path, client_id: str, output_ratio: str = "9:16") -> Path:
    """Render the fixed five-second Unified Home Remodeling end-screen frame."""
    background = (14, 20, 34)
    charcoal = (26, 29, 37)
    red = (196, 18, 48)
    gold = (250, 166, 35)
    white = (250, 250, 250)
    muted = (203, 211, 221)

    image = Image.new("RGB", (VW, VH), background)
    draw = ImageDraw.Draw(image)

    # Structured dark brand backdrop with restrained geometric accents.
    draw.rectangle((0, 0, VW, 22), fill=red)
    draw.rectangle((0, VH - 18, VW, VH), fill=gold)
    draw.polygon([(0, 0), (VW, 0), (VW, 480), (0, 770)], fill=(20, 31, 52))
    draw.polygon([(0, VH), (VW, VH), (VW, 1510), (0, 1740)], fill=charcoal)
    draw.rounded_rectangle((72, 90, VW - 72, VH - 90), radius=42, outline=(83, 93, 111), width=2)

    logo_path = get_asset_path(client_id, "logo")
    logo_y = 110
    if logo_path and Path(logo_path).exists():
        with Image.open(logo_path).convert("RGBA") as logo:
            # Double the previous maximum footprint for a stronger branded close.
            logo.thumbnail((920, 460), Image.Resampling.LANCZOS)
            logo_x = (VW - logo.width) // 2
            image.paste(logo, (logo_x, logo_y), logo)
            logo_bottom = logo_y + logo.height
    else:
        logo_font = _brand_font(58, bold=True)
        draw.text((VW // 2, logo_y + 60), "UNIFIED HOME REMODELING", font=logo_font, fill=white, anchor="mm")
        logo_bottom = logo_y + 120

    divider_y = logo_bottom + 72
    draw.line((148, divider_y, VW - 148, divider_y), fill=gold, width=4)

    headline_font = _brand_font(67, bold=True)
    draw.multiline_text(
        (VW // 2, divider_y + 165),
        "Schedule Your FREE\nConsultation Today",
        font=headline_font,
        fill=white,
        anchor="mm",
        align="center",
        spacing=8,
    )

    phone_top = divider_y + 340
    draw.rounded_rectangle((104, phone_top, VW - 104, phone_top + 132), radius=32, fill=red)
    draw.text(
        (VW // 2, phone_top + 66),
        "☎  888-631-2131",
        font=_brand_font(53, bold=True),
        fill=white,
        anchor="mm",
    )

    website_y = phone_top + 205
    draw.text(
        (VW // 2, website_y),
        "◉  UnifiedHomeRemodeling.com",
        font=_brand_font(39, bold=True),
        fill=gold,
        anchor="mm",
    )

    services_top = website_y + 120
    draw.line((164, services_top, VW - 164, services_top), fill=(83, 93, 111), width=2)
    draw.text(
        (VW // 2, services_top + 68),
        "Windows  •  Doors  •  Siding",
        font=_brand_font(36, bold=True),
        fill=muted,
        anchor="mm",
    )
    draw.text(
        (VW // 2, services_top + 122),
        "Roofing  •  And More",
        font=_brand_font(36, bold=True),
        fill=muted,
        anchor="mm",
    )

    badge_top = VH - 310
    draw.rounded_rectangle((130, badge_top, VW - 130, badge_top + 100), radius=50, outline=gold, width=3)
    draw.text(
        (VW // 2, badge_top + 50),
        "Family Owned & Operated Since 1989",
        font=_brand_font(32, bold=True),
        fill=white,
        anchor="mm",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ratio = normalized_output_ratio(output_ratio)
    preset = get_video_format(ratio)
    target = (int(preset["width"]), int(preset["height"]))
    if ratio == "16:9":
        image = _render_landscape_end_screen(client_id)
    elif target != (VW, VH):
        # Preserve all CTA copy on non-landscape crops without cutting it off.
        canvas = Image.new("RGB", target, background)
        card = ImageOps.contain(image, (int(target[0] * 0.92), int(target[1] * 0.92)), Image.Resampling.LANCZOS)
        x = (target[0] - card.width) // 2
        y = (target[1] - card.height) // 2
        canvas.paste(card, (x, y))
        image = canvas
    image.save(output_path, format="PNG")
    return output_path


def _append_supplied_vertical_outro(body_video: Path, final_video: Path) -> Path:
    """Normalize and append the supplied 9:16 Unified outro with its embedded jingle."""
    job_dir = final_video.parent
    normalized_outro = job_dir / "unified_vertical_outro.mp4"
    make_clip = [
        "ffmpeg", "-y", "-i", str(VERTICAL_OUTRO_PATH),
        "-vf", "scale=1072:1920,format=yuv420p", "-r", "30",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-movflags", "+faststart", str(normalized_outro),
    ]
    result = subprocess.run(make_clip, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Vertical outro normalization failed:\n{result.stderr[-2000:]}")
    concat_list = job_dir / "end_screen_concat.txt"
    concat_list.write_text(
        f"file '{body_video.resolve()}'\nfile '{normalized_outro.resolve()}'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", "-movflags", "+faststart", str(final_video)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Vertical outro concatenation failed:\n{result.stderr[-2000:]}")
    return final_video


def _append_branded_end_screen(body_video: Path, final_video: Path, client_id: str, output_ratio: str = "9:16") -> Path:
    """Append the supplied vertical outro or render the ratio-specific branded end screen."""
    ratio = normalized_output_ratio(output_ratio)
    if ratio == "9:16" and VERTICAL_OUTRO_PATH.exists():
        return _append_supplied_vertical_outro(body_video, final_video)
    job_dir = final_video.parent
    frame_path = job_dir / "unified_end_screen.png"
    end_clip_path = job_dir / "unified_end_screen.mp4"
    _render_end_screen(frame_path, client_id, ratio)

    if UNIFIED_JINGLE_PATH.exists():
        audio_input = ["-i", str(UNIFIED_JINGLE_PATH)]
        # The supplied 4.694-second jingle plays immediately, fades gracefully at
        # the close, and pads to the exact five-second end-screen duration.
        audio_filter = "aformat=channel_layouts=stereo,apad=pad_dur=5,atrim=duration=5,afade=t=out:st=4.20:d=0.45"
    else:
        print(f"[assembler] Warning: end-screen jingle missing at {UNIFIED_JINGLE_PATH}; using silence")
        audio_input = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        audio_filter = "atrim=duration=5"

    make_clip = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(frame_path),
        *audio_input,
        "-t", str(END_SCREEN_DURATION_SECONDS),
        "-vf", f"scale={get_video_format(normalized_output_ratio(output_ratio))['width']}:{get_video_format(normalized_output_ratio(output_ratio))['height']},format=yuv420p",
        "-af", audio_filter,
        "-r", "30",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(end_clip_path),
    ]
    result = subprocess.run(make_clip, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"End-screen render failed:\n{result.stderr[-2000:]}")

    # Both clips are normalized to the application's native 1072x1920, 30 fps,
    # H.264/AAC format. The concat demuxer therefore joins them without a second,
    # expensive full-video re-encode.
    concat_list = job_dir / "end_screen_concat.txt"
    concat_list.write_text(
        f"file '{body_video.resolve()}'\nfile '{end_clip_path.resolve()}'\n",
        encoding="utf-8",
    )
    concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy", "-movflags", "+faststart",
        str(final_video),
    ]
    result = subprocess.run(concat, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"End-screen concatenation failed:\n{result.stderr[-2000:]}")
    return final_video


def assemble_video(
    raw_video: Path,
    captions: List[Dict],
    output_path: Path,
    comedy_cues: Optional[List] = None,
    client_id: str = "unified",
    output_ratio: str = "9:16",
) -> Path:
    """Assemble the branded video body, then append the fixed five-second CTA end screen."""
    ratio = normalized_output_ratio(output_ratio)
    preset = get_video_format(ratio)
    vw, vh = int(preset["width"]), int(preset["height"])
    logo_src = get_asset_path(client_id, "logo")
    bgm_src = get_asset_path(client_id, "bgm")
    body_duration = _get_media_duration_seconds(raw_video)
    if body_duration <= 0:
        raise RuntimeError(f"Could not determine raw video duration: {raw_video}")
    laugh_src = get_asset_path(client_id, "comedy_laugh")
    applause_src = get_asset_path(client_id, "comedy_applause")

    logo_small = raw_video.parent / f"logo_small_{ratio.replace(':', 'x')}.png"
    if not logo_small.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(logo_src), "-vf", f"scale={max(160, round(vw * 0.187))}:-1", str(logo_small)],
            capture_output=True,
            check=True,
        )

    _, logo_height = _get_logo_dimensions(logo_small)
    logo_x = max(20, round(vw * 0.028))
    logo_y = vh - logo_height - max(22, round(vh * 0.018))

    # Inputs: raw video, small logo, BGM, captions, then optional comedy SFX.
    inputs = ["-i", str(raw_video), "-i", str(logo_small), "-i", str(bgm_src)]
    for caption in captions:
        inputs += ["-i", caption["png"]]

    comedy_audio_inputs = []
    if comedy_cues:
        for cue in comedy_cues:
            offset = getattr(cue, "offset_seconds", -1)
            if offset < 0:
                continue
            reaction = getattr(cue, "reaction_type", "laugh")
            duration = getattr(cue, "duration_seconds", 2.5)
            sfx_path = laugh_src if reaction == "laugh" else applause_src
            if not sfx_path.exists():
                print(f"[assembler] Warning: SFX file not found: {sfx_path}")
                continue
            idx = 3 + len(captions) + len(comedy_audio_inputs)
            inputs += ["-i", str(sfx_path)]
            comedy_audio_inputs.append((idx, offset, duration))
            print(f"[assembler] Comedy SFX: {reaction} at {offset:.2f}s (input [{idx}])")

    filter_parts = [
        f"[0:v]scale={vw}:{vh}:force_original_aspect_ratio=decrease,"
        f"pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2:color=0x0e1422[vbase]",
        f"[vbase][1:v]overlay=x={logo_x}:y={logo_y}[v0]",
    ]
    previous_video = "v0"

    for index, caption in enumerate(captions):
        input_index = index + 3
        caption_y = vh - caption["height"] - logo_height - max(35, round(vh * 0.029))
        next_video = f"v{index + 1}"
        enable = f"between(t\\,{caption['start']:.3f}\\,{caption['end']:.3f})"
        filter_parts.append(
            f"[{previous_video}][{input_index}:v]overlay=x=0:y={caption_y}:enable='{enable}'[{next_video}]"
        )
        previous_video = next_video

    filter_parts.append("[2:a]volume=0.10[bgm]")
    sfx_labels = []
    for index, (input_index, offset, duration) in enumerate(comedy_audio_inputs):
        label = f"sfx{index}"
        filter_parts.append(
            f"[{input_index}:a]atrim=duration={duration:.2f},"
            f"afade=t=out:st={max(0, duration - 0.4):.2f}:d=0.4,"
            f"adelay={int(offset * 1000)}|{int(offset * 1000)},"
            f"volume=0.75[{label}]"
        )
        sfx_labels.append(f"[{label}]")

    all_audio_count = 2 + len(sfx_labels)
    if sfx_labels:
        weights = "1 0.10" + " 0.75" * len(sfx_labels)
        filter_parts.append(
            f"[0:a][bgm]{''.join(sfx_labels)}amix=inputs={all_audio_count}:duration=longest:weights={weights},apad[aout]"
        )
    else:
        filter_parts.append("[0:a][bgm]amix=inputs=2:duration=first:weights=1 0.10,apad[aout]")

    body_video = output_path.with_name(f"{output_path.stem}_body.mp4")
    body_command = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{previous_video}]",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{body_duration:.3f}",
            "-shortest",
            "-movflags", "+faststart",
            str(body_video),
        ]
    )
    result = subprocess.run(body_command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg body assembly failed:\n{result.stderr[-2000:]}")

    try:
        _append_branded_end_screen(body_video, output_path, client_id, ratio)
    except Exception as error:
        # Do not discard an otherwise completed video if the deterministic CTA render hits an OS-level failure.
        print(f"[assembler] Warning: branded end screen failed; preserving body video: {error}")
        shutil.move(str(body_video), str(output_path))
    else:
        body_video.unlink(missing_ok=True)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[assembler] Output with end screen: {output_path.name} ({size_mb:.1f} MB)")
    return output_path
