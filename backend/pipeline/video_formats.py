"""Shared social-video output ratio presets for Unity Video Producer."""

from typing import Dict

DEFAULT_OUTPUT_RATIO = "9:16"

VIDEO_FORMATS: Dict[str, Dict[str, object]] = {
    "1:1": {
        "width": 1080,
        "height": 1080,
        "label": "Square (1:1)",
        "platform": "Instagram · Facebook Feed",
        "gpt_size": "1024x1024",
    },
    "4:5": {
        "width": 1080,
        "height": 1350,
        "label": "Portrait (4:5)",
        "platform": "Instagram · Facebook Feed",
        "gpt_size": "1024x1536",
    },
    "9:16": {
        "width": 1072,
        "height": 1920,
        "label": "Vertical (9:16)",
        "platform": "Stories · Reels · TikTok",
        "gpt_size": "1024x1536",
    },
    "16:9": {
        "width": 1920,
        "height": 1080,
        "label": "Landscape (16:9)",
        "platform": "Facebook · YouTube",
        "gpt_size": "1536x1024",
    },
}


def get_video_format(output_ratio: str) -> Dict[str, object]:
    """Return a supported preset, safely falling back to vertical video."""
    return VIDEO_FORMATS.get(output_ratio, VIDEO_FORMATS[DEFAULT_OUTPUT_RATIO])


def normalized_output_ratio(output_ratio: str) -> str:
    """Return the supported ratio key used by the rendering pipeline."""
    return output_ratio if output_ratio in VIDEO_FORMATS else DEFAULT_OUTPUT_RATIO
