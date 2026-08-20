"""
Caption rendering — Pillow PNG overlays from ElevenLabs word timestamps.
- Proper sentence case: capitalize first word of each sentence (after . ! ?)
- Always capitalize "I" as a standalone word
- Preserve known proper nouns and acronyms (Unity, Westchester, HVAC, etc.)
- Max 5 words per line
- Auto font-size reduction for long lines
- Rounded dark pill background, white bold text, drop shadow
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, List
from PIL import Image, ImageDraw, ImageFont

from .video_formats import get_video_format

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

# Words that should always be capitalized regardless of position
ALWAYS_CAPITALIZE = {
    "i",                          # pronoun
    "unity",                      # mascot name
    "unified",                    # brand name
    "westchester", "manhattan", "brooklyn", "bronx", "queens",
    "long island", "new york", "ny", "nyc",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
}

# Words that should always be ALL CAPS (acronyms)
ALWAYS_ALLCAPS = {
    "hvac", "uv", "roi", "diy", "hoa", "epa", "fha", "va",
}


def _apply_sentence_case(words: List[Dict]) -> List[Dict]:
    """
    Apply proper sentence case to a list of word dicts.
    Capitalizes the first word of each sentence and handles special cases.
    """
    result = []
    capitalize_next = True  # First word of the script is always capitalized

    for w in words:
        raw = w["word"]
        # Strip trailing punctuation to get the base word
        base = raw.rstrip(".,!?;:")
        punct = raw[len(base):]
        base_lower = base.lower()

        # Determine casing
        if base_lower in ALWAYS_ALLCAPS:
            cased = base.upper()
        elif base_lower in ALWAYS_CAPITALIZE:
            cased = base.capitalize()
        elif capitalize_next:
            cased = base.capitalize()
        else:
            cased = base.lower()

        result.append({**w, "word": cased + punct})

        # Determine if next word should be capitalized (sentence boundary)
        capitalize_next = bool(punct and re.search(r'[.!?]', punct))

    return result


def _get_font(size: int):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_captions(alignment: Dict, job_dir: Path, output_ratio: str = "9:16") -> List[Dict]:
    """
    Render caption PNGs from ElevenLabs alignment data.
    Returns list of caption dicts with timing and file paths.
    """
    cap_dir = job_dir / "captions"
    cap_dir.mkdir(exist_ok=True)
    preset = get_video_format(output_ratio)
    vw, vh = int(preset["width"]), int(preset["height"])
    scale = vw / VW
    padding_x = max(18, round(PADDING_X * scale))
    padding_y = max(12, round(PADDING_Y * scale))
    radius = max(12, round(RADIUS * scale))
    max_text_width = vw - max(60, round(80 * scale))

    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    # Build word list from character-level alignment
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

    # Apply proper sentence case across the full word list
    words = _apply_sentence_case(words)

    # Group into caption lines (max WORDS_PER_LINE words each)
    lines = []
    for i in range(0, len(words), WORDS_PER_LINE):
        group = words[i:i + WORDS_PER_LINE]
        text = " ".join(w["word"] for w in group)
        lines.append({
            "text": text,
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })

    # Render each line as a PNG
    caption_data = []
    for idx, line in enumerate(lines):
        text = line["text"]

        # Auto-size font to fit within MAX_TEXT_WIDTH
        font_size = max(30, round(54 * scale))
        min_font_size = max(18, round(28 * scale))
        font = _get_font(font_size)
        while font_size >= min_font_size:
            font = _get_font(font_size)
            tmp = Image.new("RGBA", (vw, max(200, round(200 * scale))), (0, 0, 0, 0))
            draw = ImageDraw.Draw(tmp)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            if tw <= max_text_width:
                break
            font_size -= 2

        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        box_w = tw + padding_x * 2
        box_h = th + padding_y * 2

        cap_img = Image.new("RGBA", (vw, box_h + max(12, round(20 * scale))), (0, 0, 0, 0))
        draw = ImageDraw.Draw(cap_img)
        box_x = (vw - box_w) // 2
        box_y = max(6, round(10 * scale))

        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=radius,
            fill=BG_COLOR,
        )
        text_x = box_x + padding_x
        text_y = box_y + padding_y
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
            "output_ratio": output_ratio,
            "canvas_width": vw,
            "canvas_height": vh,
        })

    # Save manifest
    manifest_path = cap_dir / "manifest.json"
    manifest_path.write_text(json.dumps(caption_data, indent=2))

    return caption_data
