"""
Caption rendering — Pillow PNG overlays from ElevenLabs word timestamps.
- Sentence case (never ALL CAPS)
- Max 5 words per line
- Auto font-size reduction for long lines
- Rounded dark pill background, white bold text, drop shadow
"""
import json
import os
from pathlib import Path
from typing import Dict, List
from PIL import Image, ImageDraw, ImageFont

VW, VH = 1072, 1920
WORDS_PER_LINE = 5
PADDING_X = 36
PADDING_Y = 20
RADIUS = 22
BG_COLOR = (0, 0, 0, 190)
TEXT_COLOR = (255, 255, 255, 255)
SHADOW_COLOR = (0, 0, 0, 210)
MAX_TEXT_WIDTH = VW - 80

FONT_PATHS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _get_font(size: int):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_captions(alignment: Dict, job_dir: Path) -> List[Dict]:
    """
    Render caption PNGs from ElevenLabs alignment data.
    Returns list of caption dicts with timing and file paths.
    """
    cap_dir = job_dir / "captions"
    cap_dir.mkdir(exist_ok=True)

    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    # Build word list
    words = []
    current_word = ""
    word_start = None
    word_end = None
    for ch, s, e in zip(chars, starts, ends):
        if ch in (" ", "\n"):
            if current_word:
                words.append({"word": current_word, "start": word_start, "end": word_end})
                current_word = ""
                word_start = None
        else:
            if word_start is None:
                word_start = s
            current_word += ch
            word_end = e
    if current_word:
        words.append({"word": current_word, "start": word_start, "end": word_end})

    # Group into lines
    lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        group = words[i:i + WORDS_PER_LINE]
        line_words = []
        for j, w in enumerate(group):
            word = w["word"].rstrip(".,!?")
            punct = w["word"][len(word):]
            if j == 0:
                line_words.append(word.capitalize() + punct)
            else:
                line_words.append(word.lower() + punct)
        lines.append({
            "text": " ".join(line_words),
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })

    # Render each line
    caption_data = []
    for idx, line in enumerate(lines):
        text = line["text"]

        # Auto-size font
        font_size = 54
        font = _get_font(font_size)
        while font_size >= 28:
            font = _get_font(font_size)
            tmp = Image.new("RGBA", (VW, 200), (0, 0, 0, 0))
            draw = ImageDraw.Draw(tmp)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            if tw <= MAX_TEXT_WIDTH:
                break
            font_size -= 2

        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        box_w = tw + PADDING_X * 2
        box_h = th + PADDING_Y * 2

        cap_img = Image.new("RGBA", (VW, box_h + 20), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cap_img)
        box_x = (VW - box_w) // 2
        box_y = 10

        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=RADIUS,
            fill=BG_COLOR,
        )
        text_x = box_x + PADDING_X
        text_y = box_y + PADDING_Y
        draw.text((text_x + 2, text_y + 2), text, font=font, fill=SHADOW_COLOR)
        draw.text((text_x, text_y), text, font=font, fill=TEXT_COLOR)

        cap_path = cap_dir / f"caption_{idx:02d}.png"
        cap_img.save(str(cap_path))

        caption_data.append({
            "index": idx,
            "text": text,
            "start": line["start"],
            "end": line["end"],
            "png": str(cap_path),
            "height": cap_img.height,
            "font_size": font_size,
        })

    # Save manifest
    manifest_path = cap_dir / "manifest.json"
    manifest_path.write_text(json.dumps(caption_data, indent=2))

    return caption_data
