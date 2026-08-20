"""
Keyframe pipeline module.
Selection priority:
  1. GPT-4.1-mini reads the full script and picks the best library keyframe by name
  2. Falls back to keyword matching on topic + format if GPT fails
  3. Falls back to generating a new keyframe with gpt-image-1 if no library match
"""
import os
import re
import base64
import requests
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps

ASSETS_DIR = Path(__file__).parent.parent / "assets"
KEYFRAMES_DIR = ASSETS_DIR / "keyframes"
REFS_DIR = ASSETS_DIR / "references"
EXTRACTED_DIR = REFS_DIR / "extracted"

from credential_store import get_credential
from .video_formats import get_video_format, normalized_output_ratio

# Keyframes used as GPT Image references — cannot be deleted
REFERENCE_KEYFRAMES = {
    "front_neutral.png",   # front-facing, clean background — primary reference
    "thumbs_up.png",       # full body, 3/4 angle
    "thinking.png",        # 3/4 angle, different pose
    "side_left.png",       # side profile
    "side_right.png",      # opposite side profile
    "back.png",            # back view
}

# Topic keyword → keyframe filename mapping (longer phrases checked first)
TOPIC_KEYFRAME_MAP = [
    # Multi-word matches (checked first — most specific)
    ("double pane", "windows.png"),
    ("double-pane", "windows.png"),
    ("entry door", "entry_doors.png"),
    ("front door", "entry_doors.png"),
    ("patio door", "patio_doors.png"),
    ("sliding door", "patio_doors.png"),
    ("french door", "patio_doors.png"),
    ("attic insulation", "insulation.png"),
    ("attic conversion", "attic_conversion.png"),
    ("energy efficiency", "energy_efficiency.png"),
    ("energy bill", "energy_efficiency.png"),
    ("utility bill", "energy_efficiency.png"),
    ("energy saving", "energy_efficiency.png"),
    ("google review", "customer_review.png"),
    ("5 star", "customer_review.png"),
    ("five star", "customer_review.png"),
    ("quick tip", "thumbs_up.png"),
    ("did you know", "thinking.png"),
    ("fun fact", "thinking.png"),
    ("myth or fact", "front_neutral.png"),
    ("back of house", "exterior_house.png"),
    ("curb appeal", "exterior_house.png"),
    ("vinyl siding", "siding.png"),
    ("fiber cement", "siding.png"),
    ("leaf guard", "gutters.png"),
    ("four season", "sunroom.png"),
    ("sun room", "sunroom.png"),
    ("flat roof", "roofing.png"),
    ("0% financing", "financing.png"),
    ("walking", "walking_street.png"),

    # Single-word matches
    ("window", "windows.png"),
    ("windows", "windows.png"),
    ("glass", "windows.png"),
    ("glazing", "windows.png"),
    ("door", "doors.png"),
    ("doors", "doors.png"),
    ("roof", "roofing.png"),
    ("roofing", "roofing.png"),
    ("shingle", "roofing.png"),
    ("siding", "siding.png"),
    ("cladding", "siding.png"),
    ("insulation", "insulation.png"),
    ("foam", "insulation.png"),
    ("gutter", "gutters.png"),
    ("gutters", "gutters.png"),
    ("downspout", "gutters.png"),
    ("drainage", "gutters.png"),
    ("exterior", "exterior_house.png"),
    ("backyard", "exterior_house.png"),
    ("bathroom", "bath_remodel.png"),
    ("bath", "bath_remodel.png"),
    ("shower", "bath_remodel.png"),
    ("vanity", "bath_remodel.png"),
    ("tile", "bath_remodel.png"),
    ("sunroom", "sunroom.png"),
    ("conservatory", "sunroom.png"),
    ("addition", "sunroom.png"),
    ("attic", "attic_conversion.png"),
    ("loft", "attic_conversion.png"),
    ("energy", "energy_efficiency.png"),
    ("solar", "energy_efficiency.png"),
    ("savings", "energy_efficiency.png"),
    ("financing", "financing.png"),
    ("finance", "financing.png"),
    ("payment", "financing.png"),
    ("loan", "financing.png"),
    ("interest", "financing.png"),
    ("review", "customer_review.png"),
    ("testimonial", "customer_review.png"),
    ("rating", "customer_review.png"),
    ("driving", "driving.png"),
    ("truck", "driving.png"),
    ("van", "driving.png"),
    ("team", "driving.png"),
    ("teaching", "teaching.png"),
    ("lesson", "teaching.png"),
    ("education", "teaching.png"),
    ("comedy", "stage_comedy.png"),
    ("joke", "stage_comedy.png"),
    ("stage", "stage_comedy.png"),
    ("question", "thinking.png"),
    ("thinking", "thinking.png"),
    ("tip", "thumbs_up.png"),
    ("thumbs", "thumbs_up.png"),
    ("street", "walking_street.png"),
    ("neighborhood", "walking_street.png"),
    ("myth", "front_neutral.png"),
    ("fact", "front_neutral.png"),
]


def _get_available_keyframes() -> list[dict]:
    """Return list of available keyframes with their filenames and labels."""
    available = []
    if not KEYFRAMES_DIR.exists():
        return available
    for f in sorted(KEYFRAMES_DIR.glob("*.png")):
        # Skip temp files
        if f.name.startswith("temp_"):
            continue
        label = f.stem.replace("_", " ").title()
        available.append({
            "filename": f.name,
            "label": label,
            "is_reference": f.name in REFERENCE_KEYFRAMES,
        })
    return available


def select_keyframe_with_gpt(script: str, topic: str, video_format: str = "") -> Path | None:
    """
    Use GPT-4.1-mini to read the full script and pick the most appropriate
    keyframe from the available library. Falls back to keyword matching on failure.
    """
    from openai import OpenAI

    available = _get_available_keyframes()
    if not available:
        return select_keyframe_keyword(topic, video_format)

    # Build a compact list of available keyframes for the prompt
    keyframe_list = "\n".join(
        f"- {kf['filename']} ({kf['label']})" for kf in available
    )

    prompt = f"""You are selecting the best background keyframe image for a Unity the golden retriever mascot video.

The video script is:
\"\"\"{script}\"\"\"

The topic is: {topic}
The format is: {video_format or 'not specified'}

Available keyframes (filename — label):
{keyframe_list}

Instructions:
- Read the script carefully and pick the single keyframe that best matches the visual context of what Unity is talking about.
- If the script is a comedy or joke, prefer stage_comedy.png.
- If the script is an announcement or promotion, prefer front_neutral.png or thumbs_up.png.
- If the script mentions a specific product (windows, doors, roofing, etc.), pick the matching product keyframe.
- If the script is a "Did you know" or trivia style, prefer thinking.png.
- If the script is a quick tip, prefer thumbs_up.png.
- If the script is a myth or fact, prefer front_neutral.png.
- Respond with ONLY the exact filename (e.g. windows.png). No explanation."""

    try:
        client = OpenAI(api_key=get_credential("openai"))
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You select keyframe filenames. Respond with only the filename."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=30,
        )
        chosen = response.choices[0].message.content.strip().lower()
        # Sanitize — strip quotes or extra text
        chosen = re.sub(r"[^a-z0-9_.]", "", chosen)
        if not chosen.endswith(".png"):
            chosen += ".png"

        path = KEYFRAMES_DIR / chosen
        if path.exists():
            print(f"[keyframe] GPT selected: {chosen}")
            return path
        else:
            print(f"[keyframe] GPT chose '{chosen}' but file not found — falling back to keyword match")
    except Exception as e:
        print(f"[keyframe] GPT selection failed ({e}) — falling back to keyword match")

    return select_keyframe_keyword(topic, video_format)


def select_keyframe_keyword(topic: str, video_format: str = "") -> Path | None:
    """Keyword-based fallback: match topic + format against the TOPIC_KEYFRAME_MAP."""
    combined = f"{topic.lower()} {video_format.lower()}"
    for keyword, filename in TOPIC_KEYFRAME_MAP:
        if keyword in combined:
            path = KEYFRAMES_DIR / filename
            if path.exists():
                return path
    # Default fallback
    default = KEYFRAMES_DIR / "front_neutral.png"
    return default if default.exists() else None


def _prepare_keyframe_canvas(source_path: Path, job_dir: Path, output_ratio: str) -> Path:
    """Fit a library or generated keyframe onto the selected social-video canvas."""
    ratio = normalized_output_ratio(output_ratio)
    preset = get_video_format(ratio)
    target = (int(preset["width"]), int(preset["height"]))
    with Image.open(source_path).convert("RGB") as source:
        if source.size == target:
            return source_path
        background = ImageOps.fit(source, target, Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=max(12, target[0] // 45)))
        foreground = ImageOps.contain(source, (int(target[0] * 0.94), int(target[1] * 0.94)), Image.Resampling.LANCZOS)
        canvas = background.copy()
        x = (target[0] - foreground.width) // 2
        y = (target[1] - foreground.height) // 2
        canvas.paste(foreground, (x, y))
        out_path = job_dir / f"keyframe_{ratio.replace(':', 'x')}.png"
        canvas.save(out_path, format="PNG")
    return out_path


def generate_new_keyframe(topic: str, job_dir: Path, scene_description: str = "", output_ratio: str = "9:16") -> Path:
    """Generate a new keyframe using gpt-image-1 edits with Unity reference images."""
    api_key = get_credential("openai")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    scene = scene_description if scene_description else f"standing in a scene related to {topic}, gesturing toward the relevant area, in a relevant environment"
    prompt = (
        f"Smooth modern 3D animation style. Unity the golden retriever mascot — "
        f"golden yellow fur, red bandana with orange house icon, simple brown leather tool belt — {scene}. "
        f"Both front paws are visibly empty: no screwdriver, hammer, wrench, sign, tool, or any handheld object. "
        f"3/4 angle showing front AND side, fluffy golden tail clearly visible. "
        f"Friendly energetic expression, mouth slightly open. "
        f"Soft warm rim lighting, professional branded video style. Full body head to paws. "
        f"Compose natively for a {get_video_format(normalized_output_ratio(output_ratio))['label']} social video frame; "
        f"keep Unity fully visible with balanced safe margins."
    )

    # Use library reference keyframes as references — multiple images for stronger character lock
    ref_priority = [
        "front_neutral.png",   # primary: clean front-facing full body
        "thumbs_up.png",       # 3/4 angle full body
        "side_left.png",       # side profile
        "thinking.png",        # alternate pose
    ]
    ref_paths = [KEYFRAMES_DIR / fn for fn in ref_priority if (KEYFRAMES_DIR / fn).exists()]

    # Fall back to references/ folder if library refs not available
    if not ref_paths:
        fallback = [
            REFS_DIR / "unity_ref_front_3q.png",
            REFS_DIR / "unity_ref_standing_full.png",
            EXTRACTED_DIR / "frame_01_start.png",
        ]
        ref_paths = [p for p in fallback if p.exists()]

    if not ref_paths:
        raise RuntimeError("No reference images found for keyframe generation")

    # Build multipart files list — send up to 4 reference images
    files = []
    for rp in ref_paths[:4]:
        files.append(("image[]", (rp.name, open(rp, "rb"), "image/png")))

    try:
        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": "gpt-image-1", "prompt": prompt, "n": "1", "size": get_video_format(normalized_output_ratio(output_ratio))["gpt_size"]},
            files=files,
            timeout=120,
        )
    finally:
        for _, (_, fh, _) in files:
            fh.close()

    if response.status_code not in (200, 201):
        raise RuntimeError(f"GPT Image failed ({response.status_code}): {response.text[:400]}")

    item = response.json()["data"][0]
    if "b64_json" in item and item["b64_json"]:
        img_bytes = base64.b64decode(item["b64_json"])
    elif "url" in item and item["url"]:
        img_bytes = requests.get(item["url"], timeout=60).content
    else:
        raise RuntimeError(f"No image data in response: {item}")

    out_path = job_dir / "keyframe.png"
    out_path.write_bytes(img_bytes)
    return _prepare_keyframe_canvas(out_path, job_dir, output_ratio)


def upload_to_cdn(local_path: Path) -> str:
    """Upload a file to fal.ai CDN and return a public URL."""
    import fal_client
    fal_key = get_credential("fal")
    client = fal_client.SyncClient(key=fal_key)
    return client.upload_file(str(local_path))


def generate_keyframe(topic: str, format: str, job_dir: Path, script: str = "", keyframe_override: str = "", client_id: str = "unified", keyframe_description: str = "", output_ratio: str = "9:16") -> str:
    """
    Main entry point: select from library or generate new keyframe.
    If keyframe_override is provided, uses that specific file directly.
    If script is provided, uses GPT-4.1-mini to pick the best match.
    Otherwise falls back to keyword matching.
    Returns CDN URL of the keyframe image.
    """
    job_dir.mkdir(parents=True, exist_ok=True)

    # User-selected keyframe override takes highest priority
    if keyframe_override:
        override_path = KEYFRAMES_DIR / keyframe_override
        if override_path.exists():
            print(f"[keyframe] Using user-selected keyframe: {keyframe_override}")
            return upload_to_cdn(_prepare_keyframe_canvas(override_path, job_dir, output_ratio))
        else:
            print(f"[keyframe] Override '{keyframe_override}' not found — falling back to auto-select")

    # If a custom scene description was provided, generate a new keyframe directly
    if keyframe_description:
        print(f"[keyframe] Generating on-the-fly keyframe: {keyframe_description}")
        generated_path = generate_new_keyframe(topic, job_dir, scene_description=keyframe_description, output_ratio=output_ratio)
        # Auto-save to library with a derived filename and label
        safe_name = re.sub(r"[^a-z0-9_]", "_", topic.lower()).strip("_") + ".png"
        library_save = KEYFRAMES_DIR / safe_name
        library_save.write_bytes(generated_path.read_bytes())
        print(f"[keyframe] Auto-saved new keyframe to library: {library_save.name}")
        # Register in main.py KEYFRAME_META via a shared update (best-effort)
        try:
            from pipeline._keyframe_registry import register_keyframe
            register_keyframe(safe_name, topic.title(), [topic.lower()])
        except Exception:
            pass
        cdn_url = upload_to_cdn(generated_path)
        print(f"[keyframe] CDN URL: {cdn_url}")
        return cdn_url

    # Try library first — use GPT selection if we have a script
    if script:
        library_path = select_keyframe_with_gpt(script, topic, format)
    else:
        library_path = select_keyframe_keyword(topic, format)

    if library_path and library_path.exists():
        print(f"[keyframe] Using library keyframe: {library_path.name}")
        cdn_url = upload_to_cdn(_prepare_keyframe_canvas(library_path, job_dir, output_ratio))
    else:
        # Generate new keyframe — no library match found
        print(f"[keyframe] No library match for '{topic}', generating new keyframe...")
        generated_path = generate_new_keyframe(topic, job_dir, output_ratio=output_ratio)
        # Auto-save to library for future reuse
        safe_name = re.sub(r"[^a-z0-9_]", "_", topic.lower()).strip("_") + ".png"
        library_save = KEYFRAMES_DIR / safe_name
        library_save.write_bytes(generated_path.read_bytes())
        print(f"[keyframe] Auto-saved new keyframe to library: {library_save.name}")
        try:
            from pipeline._keyframe_registry import register_keyframe
            register_keyframe(safe_name, topic.title(), [topic.lower()])
        except Exception:
            pass
        cdn_url = upload_to_cdn(generated_path)

    print(f"[keyframe] CDN URL: {cdn_url}")
    return cdn_url
