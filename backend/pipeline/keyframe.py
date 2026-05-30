"""
Keyframe generation — Leonardo.ai with Unity 3/4-angle reference.
Generates a single 9:16 keyframe image for Kling Avatar v2.
"""
import os
import time
import subprocess
import requests
from pathlib import Path

LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
ASSETS_DIR = Path(__file__).parent.parent / "assets"
REF_3Q = ASSETS_DIR / "references" / "unity_ref_front_3q.png"

# Leonardo Diffusion XL model
MODEL_ID = "ac614f96-1082-45bf-be9d-757f2d31c174"

SCENE_DESCRIPTIONS = {
    "doors":       "standing in front of a modern front door, gesturing toward it",
    "windows":     "standing next to a large double-pane window in a bright living room, gesturing toward it",
    "roofing":     "standing on a rooftop with a clear sky background, pointing upward",
    "siding":      "standing in front of a house with fresh new siding, gesturing toward the wall",
    "insulation":  "standing in an attic space with visible insulation, gesturing around",
    "gutters":     "standing next to a house with clean gutters, pointing upward",
    "permits":     "standing at a construction site with blueprints, looking at the camera",
    "energy":      "standing in a bright modern home, surrounded by energy-efficient elements",
    "default":     "standing in a bright modern home interior, speaking directly to the camera",
}


def get_scene_description(topic: str) -> str:
    """Match topic to a scene description."""
    topic_lower = topic.lower()
    for key, desc in SCENE_DESCRIPTIONS.items():
        if key in topic_lower:
            return desc
    return SCENE_DESCRIPTIONS["default"]


def generate_keyframe(topic: str, format: str, job_dir: Path) -> str:
    """
    Generate a Unity keyframe image and return its CDN URL.
    Uploads the reference image, generates with Leonardo.ai, returns URL.
    """
    if not LEONARDO_API_KEY:
        raise RuntimeError("LEONARDO_API_KEY not set")

    scene = get_scene_description(topic)
    prompt = (
        f"Smooth modern 3D animation style. Unity the golden retriever mascot — "
        f"golden yellow fur, red bandana with small house icon, brown leather tool belt "
        f"with wrench and hammer — {scene}. "
        f"3/4 angle showing front AND side, fluffy golden tail clearly visible. "
        f"Friendly energetic expression, mouth slightly open. "
        f"Soft rim lighting, professional branded video style. Full body head to tail. "
        f"Clean background, no text signs on wall."
    )

    headers = {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json",
    }

    # Upload reference image
    ref_url = _upload_reference(headers)

    # Generate image
    payload = {
        "modelId": MODEL_ID,
        "prompt": prompt,
        "negative_prompt": "missing tail, no tail, human hands, distorted face, blurry, text signs, watermark",
        "num_images": 1,
        "width": 608,
        "height": 1080,
        "guidance_scale": 7,
        "num_inference_steps": 30,
        "public": False,
        "controlnets": [
            {
                "initImageId": ref_url,
                "initImageType": "UPLOADED",
                "preprocessorId": 100,  # Character reference
                "strengthType": "Mid",
            }
        ] if ref_url else [],
    }

    r = requests.post(
        "https://cloud.leonardo.ai/api/rest/v1/generations",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Leonardo generation failed ({r.status_code}): {r.text[:300]}")

    gen_id = r.json()["sdGenerationJob"]["generationId"]

    # Poll for completion
    for _ in range(60):
        time.sleep(3)
        gr = requests.get(
            f"https://cloud.leonardo.ai/api/rest/v1/generations/{gen_id}",
            headers=headers,
            timeout=15,
        )
        gd = gr.json()
        gen = gd.get("generations_by_pk", {})
        status = gen.get("status", "PENDING")
        if status == "COMPLETE":
            images = gen.get("generated_images", [])
            if images:
                img_url = images[0]["url"]
                # Download and save locally
                img_data = requests.get(img_url, timeout=30).content
                local_path = job_dir / "keyframe.png"
                local_path.write_bytes(img_data)
                # Upload to CDN for fal.ai
                cdn_url = _upload_to_cdn(local_path)
                return cdn_url
            raise RuntimeError("No images in Leonardo response")
        elif status == "FAILED":
            raise RuntimeError("Leonardo generation failed")

    raise RuntimeError("Leonardo generation timed out")


def _upload_reference(headers: dict) -> str:
    """Upload Unity reference image to Leonardo and return image ID."""
    try:
        # Get presigned URL
        r = requests.post(
            "https://cloud.leonardo.ai/api/rest/v1/init-image",
            headers=headers,
            json={"extension": "png"},
            timeout=15,
        )
        if r.status_code not in (200, 201):
            return ""
        data = r.json()
        upload_url = data.get("uploadInitImage", {}).get("url", "")
        fields = data.get("uploadInitImage", {}).get("fields", {})
        image_id = data.get("uploadInitImage", {}).get("id", "")

        if not upload_url:
            return ""

        # Upload the file
        with open(REF_3Q, "rb") as f:
            img_data = f.read()

        files = {k: (None, v) for k, v in fields.items()}
        files["file"] = ("unity_ref.png", img_data, "image/png")
        requests.post(upload_url, files=files, timeout=30)
        return image_id
    except Exception:
        return ""


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
    # Extract URL from output (last line)
    lines = result.stdout.strip().split("\n")
    for line in reversed(lines):
        if line.startswith("http"):
            return line.strip()
    raise RuntimeError(f"Could not parse CDN URL from: {result.stdout}")
