"""
Unity Video Producer — FastAPI Backend
Async job queue for AI video generation pipeline.
"""
import os
import uuid
import asyncio
import logging
import base64
import re
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests as http_requests

from pipeline.orchestrator import run_pipeline, JOB_STORE, JobStatus, update_job, KEYFRAME_APPROVAL_EVENTS, KEYFRAME_APPROVAL_DECISIONS
from pipeline.client_config import get_client, list_clients, reload_clients
from pipeline.script_writer import generate_script
from pipeline._keyframe_registry import set_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unity Video Producer", version="1.0.0")

# CORS — allow frontend dev server and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve finished videos
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# Serve frontend build (if present)
FRONTEND_BUILD = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_BUILD.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_BUILD), html=True), name="frontend")


# ─── Request / Response Models ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str
    format: str  # "myth_or_fact" | "quick_tip" | "did_you_know" | "comedy" | "announcement" | "story"
    length: str  # "8s" | "15s" | "20s"
    custom_script: Optional[str] = None  # override auto-generated script
    keyframe_override: Optional[str] = None  # filename from library, e.g. "windows.png"; None = auto-select
    keyframe_description: Optional[str] = None  # describe a new scene to generate on-the-fly
    client_id: str = "unified"  # multi-tenant: which client config to use


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    progress: Optional[int] = None  # 0–100
    error: Optional[str] = None
    video_url: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "Unity Video Producer"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Start a new video generation job."""
    job_id = str(uuid.uuid4())
    JOB_STORE[job_id] = JobStatus(
        job_id=job_id,
        status="queued",
        step="Queued",
        progress=0,
    )
    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        topic=req.topic,
        format=req.format,
        length=req.length,
        custom_script=req.custom_script,
        keyframe_override=req.keyframe_override,
        keyframe_description=req.keyframe_description,
        client_id=req.client_id,
    )
    logger.info(f"Job {job_id} queued: {req.topic} / {req.format} / {req.length}")
    return GenerateResponse(
        job_id=job_id,
        status="queued",
        message="Video generation started. Poll /status/{job_id} for updates.",
    )


@app.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str):
    """Poll job status and progress."""
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        step=job.step,
        progress=job.progress,
        error=job.error,
        video_url=job.video_url,
    )


@app.get("/download/{job_id}")
def download(job_id: str):
    """Download the finished video."""
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail=f"Job not complete (status: {job.status})")
    video_path = OUTPUTS_DIR / f"{job_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"unity_{job_id[:8]}.mp4",
    )


@app.get("/jobs")
def list_jobs(client_id: Optional[str] = None):
    """List all jobs (most recent first). Optionally filter by client_id."""
    jobs = list(JOB_STORE.values())
    if client_id:
        jobs = [j for j in jobs if j.client_id == client_id]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [
        {
            "job_id": j.job_id,
            "status": j.status,
            "step": j.step,
            "progress": j.progress,
            "topic": j.topic,
            "format": j.format,
            "length": j.length,
            "client_id": j.client_id,
            "created_at": j.created_at,
            "video_url": j.video_url,
            "script": j.script,
            "keyframe_url": j.keyframe_url,
            "keyframe_label": j.keyframe_label,
            "error": j.error,
        }
        for j in jobs[:50]  # last 50 jobs
    ]


@app.post("/jobs/{job_id}/approve-keyframe")
async def approve_keyframe(job_id: str):
    """Approve the generated keyframe and resume the pipeline."""
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "waiting_keyframe_approval":
        raise HTTPException(status_code=400, detail=f"Job is not waiting for keyframe approval (status: {job.status})")
    event = KEYFRAME_APPROVAL_EVENTS.get(job_id)
    if not event:
        raise HTTPException(status_code=500, detail="Approval event not found")
    KEYFRAME_APPROVAL_DECISIONS[job_id] = "approved"
    event.set()
    return {"status": "approved", "message": "Keyframe approved — pipeline resuming"}


class RegenerateKeyframeRequest(BaseModel):
    description: Optional[str] = None  # optional new description; if None, reuses original


@app.post("/jobs/{job_id}/regenerate-keyframe")
async def regenerate_keyframe(job_id: str, req: RegenerateKeyframeRequest = RegenerateKeyframeRequest()):
    """Reject the generated keyframe and regenerate with optional new description."""
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "waiting_keyframe_approval":
        raise HTTPException(status_code=400, detail=f"Job is not waiting for keyframe approval (status: {job.status})")
    event = KEYFRAME_APPROVAL_EVENTS.get(job_id)
    if not event:
        raise HTTPException(status_code=500, detail="Approval event not found")
    KEYFRAME_APPROVAL_DECISIONS[job_id] = "regenerate"
    if req.description:
        KEYFRAME_APPROVAL_DECISIONS[f"{job_id}_new_description"] = req.description
    event.set()
    return {"status": "regenerating", "message": "Regenerating keyframe..."}


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job from history (and its output file if present)."""
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOB_STORE[job_id]
    if job.status in ("queued", "running"):
        raise HTTPException(status_code=400, detail="Cannot delete a job that is still running")
    # Remove video file if it exists
    video_path = OUTPUTS_DIR / f"{job_id}.mp4"
    if video_path.exists():
        video_path.unlink()
    # Remove job dir (captions, voice, etc.)
    job_dir = OUTPUTS_DIR / job_id
    if job_dir.exists():
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
    del JOB_STORE[job_id]
    # Persist updated store
    from pipeline.orchestrator import _save_jobs
    _save_jobs()
    return {"message": f"Job {job_id} deleted"}


@app.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, background_tasks: BackgroundTasks):
    """Re-queue a failed job with its original parameters."""
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail=f"Only failed jobs can be retried (status: {job.status})")

    new_job_id = str(uuid.uuid4())
    JOB_STORE[new_job_id] = JobStatus(
        job_id=new_job_id,
        status="queued",
        step="Queued",
        progress=0,
        topic=job.original_topic or job.topic,
        format=job.original_format or job.format,
        length=job.original_length or job.length,
        client_id=job.client_id,
    )
    background_tasks.add_task(
        run_pipeline,
        job_id=new_job_id,
        topic=job.original_topic or job.topic,
        format=job.original_format or job.format,
        length=job.original_length or job.length,
        custom_script=job.original_custom_script,
        keyframe_override=job.original_keyframe_override,
        keyframe_description=job.original_keyframe_description,
        client_id=job.client_id,
    )
    logger.info(f"Retry job {new_job_id} queued (original: {job_id})")
    return {"job_id": new_job_id, "status": "queued", "message": "Retry queued"}


class PreviewScriptRequest(BaseModel):
    topic: str
    format: str
    length: str
    client_id: str = "unified"


@app.post("/preview-script")
async def preview_script(req: PreviewScriptRequest):
    """Generate a script preview without starting a video job."""
    try:
        script = await asyncio.to_thread(
            generate_script, req.topic, req.format, req.length, req.client_id
        )
        return {"script": script}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Script generation failed: {str(e)}")


class PromptMagicRequest(BaseModel):
    description: str
    client_id: str = "unified"


@app.post("/prompt-magic")
async def prompt_magic(req: PromptMagicRequest):
    """Take a raw keyframe description and optimize it into a high-quality image generation prompt."""
    import os
    from openai import OpenAI
    openai_client = OpenAI()
    cfg = get_client(req.client_id)
    mascot_name = cfg.get("mascot_name", "Unity")
    mascot_desc = cfg.get("mascot_description", "a friendly golden retriever with a red bandana and tool belt")
    system_prompt = f"""You are an expert AI image generation prompt engineer for a mascot character named {mascot_name}.

The character's appearance is ALWAYS handled automatically by the image model — you must NEVER describe the character's physical appearance (fur color, clothing, accessories, ears, tail, bandana, tool belt, etc.).

Your ONLY job is to optimize the SCENE description: the environment, setting, action, pose, props, lighting, and background.

Rules:
- NEVER mention the character's appearance, breed, clothing, or accessories
- ALWAYS start with what the character is DOING and WHERE (action + environment)
- Add specific scene details: lighting quality, background elements, perspective/camera angle, time of day, art style
- Include: "photorealistic digital illustration", "warm natural lighting"
- Describe props, objects, and environment the character interacts with
- Specify pose and expression in terms of action only (e.g. "leaning forward confidently", "pointing at the window")
- Keep it under 150 words
- Output ONLY the optimized scene prompt, no explanation or preamble

Example input: "Unity next to a foggy window"
Example output: "Standing beside a large residential window covered in condensation, one paw pressed against the glass and the other pointing at the fog, indoor setting with soft morning light filtering through, warm interior background with wood floors, photorealistic digital illustration, shallow depth of field"""

    user_message = f"Scene description: {req.description}"

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        optimized = response.choices[0].message.content.strip()
        return {"optimized_prompt": optimized}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prompt optimization failed: {str(e)}")


@app.get("/clients")
def list_clients_endpoint():
    """List all active clients with their config (excluding sensitive credentials)."""
    result = []
    for cid in list_clients():
        cfg = get_client(cid)
        result.append({
            "client_id": cid,
            "brand_name": cfg.get("brand_name"),
            "mascot_name": cfg.get("mascot_name"),
            "industry": cfg.get("industry"),
            "active": cfg.get("active", True),
        })
    return result


@app.post("/clients/reload")
def reload_clients_endpoint():
    """Reload clients.json from disk (use after editing the file)."""
    clients = reload_clients()
    return {"message": f"Reloaded {len(clients)} client(s)", "clients": list(clients.keys())}


# ─── Keyframe Library ───────────────────────────────────────────────────────────

KEYFRAMES_DIR = Path(__file__).parent / "assets" / "keyframes"

# NOTE: @app.delete("/keyframes/{filename}") MUST be defined BEFORE the StaticFiles mount
# because the mount intercepts ALL requests to /keyframes/* including DELETE.
# FastAPI processes routes in registration order — explicit routes registered first win.

@app.delete("/keyframes/{filename}")
def delete_keyframe(filename: str):
    """Delete a keyframe from the library. Reference keyframes cannot be deleted."""
    from pipeline.keyframe import REFERENCE_KEYFRAMES
    if filename in REFERENCE_KEYFRAMES:
        raise HTTPException(status_code=403, detail="Reference keyframes cannot be deleted — they are used for AI image generation consistency.")
    path = KEYFRAMES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Keyframe not found")
    path.unlink()
    KEYFRAME_META.pop(filename, None)
    return {"message": f"Keyframe {filename} deleted"}

# Serve keyframe images as static files (registered AFTER delete endpoint)
if KEYFRAMES_DIR.exists():
    app.mount("/keyframes", StaticFiles(directory=str(KEYFRAMES_DIR)), name="keyframes")

# Keyframe metadata — human-readable labels and keyword tags
KEYFRAME_META = {
    "windows.png":          {"label": "Windows",             "tags": ["window", "double pane", "glass", "glazing"]},
    "doors.png":            {"label": "Doors (General)",     "tags": ["door", "doors"]},
    "entry_doors.png":      {"label": "Entry Doors",         "tags": ["entry door", "front door"]},
    "patio_doors.png":      {"label": "Patio / Sliding Doors", "tags": ["patio door", "sliding door", "french door"]},
    "roofing.png":          {"label": "Roofing",             "tags": ["roof", "roofing", "shingle", "flat roof"]},
    "siding.png":           {"label": "Siding",              "tags": ["siding", "cladding", "vinyl siding", "fiber cement"]},
    "insulation.png":       {"label": "Insulation",          "tags": ["insulation", "foam", "attic insulation"]},
    "gutters.png":          {"label": "Gutters",             "tags": ["gutter", "gutters", "downspout", "leaf guard"]},
    "exterior_house.png":   {"label": "Exterior / Back of House", "tags": ["exterior", "backyard", "back of house", "curb appeal"]},
    "bath_remodel.png":     {"label": "Bathroom Remodel",   "tags": ["bathroom", "bath", "shower", "vanity", "tile"]},
    "sunroom.png":          {"label": "Sunroom / Addition", "tags": ["sunroom", "four season", "sun room", "conservatory"]},
    "attic_conversion.png": {"label": "Attic Conversion",   "tags": ["attic conversion", "attic", "loft"]},
    "energy_efficiency.png":{"label": "Energy Efficiency",  "tags": ["energy efficiency", "energy bill", "utility bill", "solar", "savings"]},
    "financing.png":        {"label": "Financing",          "tags": ["financing", "finance", "payment", "loan", "0% financing"]},
    "customer_review.png":  {"label": "Customer Reviews",   "tags": ["review", "testimonial", "5 star", "google review"]},
    "driving.png":          {"label": "Driving / On the Road", "tags": ["driving", "truck", "van", "team"]},
    "teaching.png":         {"label": "Teaching / Presenting", "tags": ["teaching", "lesson", "education"]},
    "stage_comedy.png":     {"label": "Comedy / Stage",     "tags": ["comedy", "joke", "stage"]},
    "walking_street.png":   {"label": "Walking the Street", "tags": ["walking", "street", "neighborhood"]},
    "front_neutral.png":    {"label": "Neutral / Myth or Fact", "tags": ["myth or fact", "myth", "fact", "neutral"]},
    "thinking.png":         {"label": "Thinking / Did You Know", "tags": ["thinking", "did you know", "fun fact", "question"]},
    "thumbs_up.png":        {"label": "Thumbs Up / Quick Tip", "tags": ["thumbs up", "quick tip", "tip"]},
    "side_left.png":        {"label": "Side View (Left)",   "tags": ["side left", "profile"]},
    "side_right.png":       {"label": "Side View (Right)",  "tags": ["side right", "profile"]},
    "back.png":             {"label": "Back View",          "tags": ["back", "behind"]},
}

# Share KEYFRAME_META with the pipeline registry so new keyframes auto-register
set_registry(KEYFRAME_META)


@app.get("/keyframes-list")
def list_keyframes():
    """List all available keyframes with metadata and preview URLs."""
    from pipeline.keyframe import REFERENCE_KEYFRAMES
    result = []
    for filename, meta in KEYFRAME_META.items():
        path = KEYFRAMES_DIR / filename
        if path.name.startswith("temp_"):
            continue
        result.append({
            "filename": filename,
            "label": meta["label"],
            "tags": meta["tags"],
            "url": f"/keyframes/{filename}",
            "available": path.exists(),
            "is_reference": filename in REFERENCE_KEYFRAMES,
        })
    # Also include any keyframes on disk not in metadata
    if KEYFRAMES_DIR.exists():
        known = set(KEYFRAME_META.keys())
        for f in sorted(KEYFRAMES_DIR.glob("*.png")):
            if f.name in known or f.name.startswith("temp_"):
                continue
            result.append({
                "filename": f.name,
                "label": f.stem.replace("_", " ").title(),
                "tags": [],
                "url": f"/keyframes/{f.name}",
                "available": True,
                "is_reference": f.name in REFERENCE_KEYFRAMES,
            })
    return result


# ─── Keyframe Creator ────────────────────────────────────────────────────────

REFERENCES_DIR = Path(__file__).parent / "assets" / "references"

class KeyframeGenerateRequest(BaseModel):
    scene_description: str  # plain English description of the scene
    label: str              # human-readable name, e.g. "Garage Door"

class KeyframeGenerateResponse(BaseModel):
    image_b64: str          # base64-encoded PNG for preview
    temp_filename: str      # temp file saved server-side for save step

class KeyframeSaveRequest(BaseModel):
    temp_filename: str      # from generate response
    label: str              # human-readable label
    filename: str           # e.g. "garage_door.png"
    tags: List[str] = []    # optional keyword tags


@app.post("/generate-keyframe", response_model=KeyframeGenerateResponse)
async def generate_keyframe_endpoint(req: KeyframeGenerateRequest):
    """Generate a new Unity keyframe using GPT Image with reference frames."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Build the prompt — same style as the production pipeline
    prompt = (
        f"Smooth modern 3D Pixar-style animation. Unity the golden retriever mascot of Unified Home Remodeling. "
        f"Unity has golden yellow fur, a red triangular bandana with a small house icon on it, "
        f"a brown leather tool belt with a wrench and hammer, floppy ears, a fluffy tail, and a friendly smile. "
        f"Scene: {req.scene_description}. "
        f"Portrait orientation (9:16), full body visible, Unity centered in frame. "
        f"Bright, warm, professional lighting. No text or watermarks."
    )

    # Load reference images — prioritize extracted video frames for best consistency
    ref_files = []
    extracted_dir = REFERENCES_DIR / "extracted"
    if extracted_dir.exists():
        ref_files += sorted(extracted_dir.glob("*.png"))[:4]  # up to 4 extracted frames
    if REFERENCES_DIR.exists():
        ref_files += [REFERENCES_DIR / "unity_ref_front_3q.png"]  # original front reference

    if not ref_files:
        raise HTTPException(status_code=500, detail="No reference images found on server")

    # Call GPT Image edits endpoint
    files = []
    opened = []
    try:
        for i, ref_path in enumerate(ref_files[:5]):  # max 5 references
            if ref_path.exists():
                f = open(ref_path, "rb")
                opened.append(f)
                files.append(("image[]", (ref_path.name, f, "image/png")))

        data = {"prompt": prompt, "model": "gpt-image-1", "size": "1024x1536", "n": "1"}
        headers = {"Authorization": f"Bearer {openai_key}"}

        resp = http_requests.post(
            "https://api.openai.com/v1/images/edits",
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
    finally:
        for f in opened:
            f.close()

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"GPT Image error: {resp.text[:300]}")

    result = resp.json()
    img_data = result["data"][0]

    # Get image as base64
    if "b64_json" in img_data:
        img_b64 = img_data["b64_json"]
    elif "url" in img_data:
        img_resp = http_requests.get(img_data["url"], timeout=60)
        img_b64 = base64.b64encode(img_resp.content).decode()
    else:
        raise HTTPException(status_code=500, detail="No image data in response")

    # Save to a temp file so the save step can retrieve it
    temp_filename = f"temp_{uuid.uuid4().hex[:8]}.png"
    temp_path = KEYFRAMES_DIR / temp_filename
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    with open(temp_path, "wb") as f:
        f.write(base64.b64decode(img_b64))

    return KeyframeGenerateResponse(image_b64=img_b64, temp_filename=temp_filename)


@app.post("/save-keyframe")
def save_keyframe(req: KeyframeSaveRequest):
    """Save a generated keyframe to the permanent library."""
    # Validate filename
    safe_name = re.sub(r"[^a-z0-9_]", "", req.filename.lower().replace(" ", "_").replace("-", "_"))
    if not safe_name.endswith(".png"):
        safe_name += ".png"

    temp_path = KEYFRAMES_DIR / req.temp_filename
    if not temp_path.exists():
        raise HTTPException(status_code=404, detail="Temp keyframe not found — please regenerate")

    # Move temp file to permanent name
    final_path = KEYFRAMES_DIR / safe_name
    temp_path.rename(final_path)

    # Add to in-memory metadata
    KEYFRAME_META[safe_name] = {
        "label": req.label,
        "tags": req.tags,
    }

    return {
        "filename": safe_name,
        "label": req.label,
        "url": f"/keyframes/{safe_name}",
        "message": f"Keyframe '{req.label}' saved to library as {safe_name}",
    }


# ─── Graphic Generation Endpoints ────────────────────────────────────────────
# Appended below the existing endpoints in main.py

# Pydantic models for graphic generation
class GraphicGenerateRequest(BaseModel):
    content_type: str           # "tip_card" | "before_after" | "carousel" | "testimonial" | "promotional"
    size_ratio: str             # "1:1" | "4:5" | "9:16" | "16:9"
    user_prompt: str            # what the graphic should say/show
    client_id: str = "unified"
    total_slides: int = 1       # for carousel: total number of slides
    slide_num: int = 1          # for carousel: which slide this is

class GraphicGenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str

class GraphicStatusResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    progress: Optional[int] = None
    error: Optional[str] = None
    image_url: Optional[str] = None
    image_b64: Optional[str] = None

# In-memory store for graphic jobs (separate from video jobs)
GRAPHIC_JOB_STORE: dict = {}

# Graphic outputs directory
GRAPHICS_DIR = Path(__file__).parent / "outputs" / "graphics"
GRAPHICS_DIR.mkdir(parents=True, exist_ok=True)

# Size presets
GRAPHIC_SIZE_PRESETS = {
    "1:1":  {"width": 1024, "height": 1024,  "label": "Square — Instagram/Facebook Feed"},
    "4:5":  {"width": 1024, "height": 1280,  "label": "Portrait — Instagram/Facebook Feed"},
    "9:16": {"width": 1024, "height": 1792,  "label": "Vertical — Stories/Reels/TikTok"},
    "16:9": {"width": 1792, "height": 1024,  "label": "Landscape — Facebook/YouTube Cover"},
}

# Brand identity constants
BRAND_RED    = (196, 18, 48)    # #C41230
BRAND_GOLD   = (245, 166, 35)   # #F5A623
BRAND_DARK   = (26, 26, 26)     # #1A1A1A
BRAND_WHITE  = (255, 255, 255)  # #FFFFFF

# Content type prompt templates
GRAPHIC_CONTENT_PROMPTS = {
    "tip_card": """Create a professional branded social media tip card graphic for Unified Home Remodeling.
Layout: Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt with wrench and hammer, floppy ears, fluffy tail, friendly smile) stands on the LEFT side, taking up about 40% of the width, pointing at or gesturing toward the text.
RIGHT side: large bold white headline text on a dark charcoal (#1A1A1A) background with a supporting tip or fact below in smaller text.
Accent colors: deep red (#C41230) for highlights and borders, gold (#F5A623) for emphasis.
IMPORTANT: Leave the bottom 9% of the image as a SOLID deep red (#C41230) horizontal bar with absolutely NO text, logos, or graphics in it — this area will be used for a programmatic logo overlay.
Smooth 3D cartoon style for Unity. Clean modern layout. No clutter.
Content to include: {user_prompt}""",

    "before_after": """Create a professional before/after social media graphic for Unified Home Remodeling.
Split layout: LEFT half labeled "BEFORE" (old/worn/damaged state), RIGHT half labeled "AFTER" (new/beautiful/finished state).
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) stands at the CENTER dividing line, arms spread wide gesturing to both sides with a proud expression.
Bold white "BEFORE" label on left, bold white "AFTER" label on right. Deep red (#C41230) center dividing line.
Dark charcoal (#1A1A1A) overall tone. Gold (#F5A623) accent details.
IMPORTANT: Leave the bottom 9% of the image as a SOLID deep red (#C41230) horizontal bar with absolutely NO text, logos, or graphics in it — this area will be used for a programmatic logo overlay.
Smooth 3D cartoon style for Unity.
Content description: {user_prompt}""",

    "carousel": """Create a professional social media carousel slide graphic for Unified Home Remodeling.
This is slide {slide_num} of {total_slides}. Show a small "{slide_num}/{total_slides}" indicator in the top-right corner in gold (#F5A623).
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) appears as a guide — pointing at content or gesturing toward text.
Dark charcoal (#1A1A1A) background, white body text, deep red (#C41230) headline accent.
IMPORTANT: Leave the bottom 9% of the image as a SOLID deep red (#C41230) horizontal bar with absolutely NO text, logos, or graphics in it — this area will be used for a programmatic logo overlay.
Smooth 3D cartoon style for Unity. Clean modern layout.
Slide content: {user_prompt}""",

    "testimonial": """Create a professional customer testimonial social media graphic for Unified Home Remodeling.
Large white opening quote mark. Customer quote text prominently displayed in white. Five gold (#F5A623) stars prominently displayed.
Customer name and location in smaller text below the quote.
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) in the corner giving a thumbs up or smiling warmly.
Dark charcoal (#1A1A1A) background with a deep red (#C41230) accent border or stripe on the left edge.
IMPORTANT: Leave the bottom 9% of the image as a SOLID deep red (#C41230) horizontal bar with absolutely NO text, logos, or graphics in it — this area will be used for a programmatic logo overlay.
Smooth 3D cartoon style for Unity. Trustworthy, warm design.
Testimonial content: {user_prompt}""",

    "promotional": """Create a professional promotional social media graphic for Unified Home Remodeling.
Bold attention-grabbing headline in large white text. Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) featured prominently — excited, energetic, pointing at the offer.
Deep red (#C41230) dominant background with dark charcoal (#1A1A1A) and gold (#F5A623) accents.
Clear offer text and call-to-action area in the center.
IMPORTANT: Leave the bottom 9% of the image as a SOLID deep red (#C41230) horizontal bar with absolutely NO text, logos, or graphics in it — this area will be used for a programmatic logo overlay.
Smooth 3D cartoon style for Unity. Bold, modern, high-contrast design.
Promotional content: {user_prompt}""",
}


def _build_graphic_prompt(content_type: str, user_prompt: str, size_ratio: str,
                           slide_num: int = 1, total_slides: int = 1) -> str:
    template = GRAPHIC_CONTENT_PROMPTS.get(content_type, GRAPHIC_CONTENT_PROMPTS["tip_card"])
    prompt = template.format(user_prompt=user_prompt, slide_num=slide_num, total_slides=total_slides)
    size_info = GRAPHIC_SIZE_PRESETS.get(size_ratio, GRAPHIC_SIZE_PRESETS["1:1"])
    prompt += f"\nAspect ratio: {size_ratio} ({size_info['label']}). Compose the layout to fill this format."
    return prompt.strip()


async def _run_graphic_pipeline(job_id: str, req: GraphicGenerateRequest,
                                 uploaded_image_path: Optional[str] = None):
    """Background task: generate the graphic and update job store."""
    import asyncio

    def update_graphic_job(status, step=None, progress=None, error=None,
                            image_url=None, image_b64=None):
        GRAPHIC_JOB_STORE[job_id].update({
            "status": status,
            "step": step,
            "progress": progress,
            "error": error,
            "image_url": image_url,
            "image_b64": image_b64,
        })

    try:
        update_graphic_job("running", "Generating graphic with GPT Image...", 20)

        client = get_client(req.client_id)
        assets_base = Path(__file__).parent / "assets"

        # Build prompt
        prompt = _build_graphic_prompt(
            req.content_type, req.user_prompt, req.size_ratio,
            req.slide_num, req.total_slides
        )

        # Get Unity reference images
        refs_dir = assets_base / "references"
        priority_refs = [
            "unity_ref_front_3q.png",
            "unity_ref_front.png",
            "unity_ref_standing_full.png",
            "unity_extracted_01.png",
        ]
        ref_files = []
        for ref in priority_refs:
            p = refs_dir / ref
            if p.exists():
                ref_files.append(p)
            if len(ref_files) >= 3:
                break

        # Determine output size
        size_preset = GRAPHIC_SIZE_PRESETS.get(req.size_ratio, GRAPHIC_SIZE_PRESETS["1:1"])
        width = size_preset["width"]
        height = size_preset["height"]

        # Output path
        output_filename = f"graphic_{job_id[:8]}.png"
        output_path = GRAPHICS_DIR / output_filename

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        opened = []

        try:
            if ref_files or uploaded_image_path:
                # Use edits endpoint with references
                files = []
                if uploaded_image_path and Path(uploaded_image_path).exists():
                    f = open(uploaded_image_path, "rb")
                    opened.append(f)
                    files.append(("image[]", (Path(uploaded_image_path).name, f, "image/png")))
                for ref_path in ref_files:
                    f = open(ref_path, "rb")
                    opened.append(f)
                    files.append(("image[]", (ref_path.name, f, "image/png")))

                form_data = {
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": "1",
                    "size": f"{width}x{height}",
                    "quality": "medium",
                }
                headers = {"Authorization": f"Bearer {openai_key}"}
                resp = http_requests.post(
                    "https://api.openai.com/v1/images/edits",
                    headers=headers,
                    files=files,
                    data=form_data,
                    timeout=120,
                )
            else:
                # Pure text-to-image
                payload = {
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": f"{width}x{height}",
                    "quality": "medium",
                }
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                }
                resp = http_requests.post(
                    "https://api.openai.com/v1/images/generations",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
        finally:
            for f in opened:
                f.close()

        if resp.status_code != 200:
            raise Exception(f"GPT Image API error {resp.status_code}: {resp.text[:300]}")

        update_graphic_job("running", "Saving graphic...", 80)

        result = resp.json()
        img_data = result["data"][0]

        if "b64_json" in img_data:
            img_b64 = img_data["b64_json"]
            output_path.write_bytes(base64.b64decode(img_b64))
        elif "url" in img_data:
            img_resp = http_requests.get(img_data["url"], timeout=60)
            output_path.write_bytes(img_resp.content)
            img_b64 = base64.b64encode(img_resp.content).decode()
        else:
            raise Exception("No image data in API response")

        # ── Pillow post-processing: overlay real logo on footer bar ──────────
        update_graphic_job("running", "Applying brand logo...", 90)
        try:
            from PIL import Image as PILImage
            logo_path = assets_base / "unified_logo_real.png"
            if logo_path.exists():
                base_img = PILImage.open(output_path).convert("RGBA")
                img_w, img_h = base_img.size
                footer_h = max(60, int(img_h * 0.09))  # 9% of height, min 60px

                # Draw solid red footer bar
                from PIL import ImageDraw
                draw = ImageDraw.Draw(base_img)
                draw.rectangle(
                    [(0, img_h - footer_h), (img_w, img_h)],
                    fill=(196, 18, 48, 255)  # #C41230 fully opaque
                )

                # Scale logo to fit footer with padding
                logo_img = PILImage.open(logo_path).convert("RGBA")
                logo_w, logo_h = logo_img.size
                max_logo_h = int(footer_h * 0.72)
                scale = max_logo_h / logo_h
                new_logo_w = int(logo_w * scale)
                new_logo_h = max_logo_h
                logo_resized = logo_img.resize((new_logo_w, new_logo_h), PILImage.LANCZOS)

                # Center logo in footer bar
                logo_x = (img_w - new_logo_w) // 2
                logo_y = img_h - footer_h + (footer_h - new_logo_h) // 2
                base_img.paste(logo_resized, (logo_x, logo_y), logo_resized)

                # Save final composite
                base_img.convert("RGB").save(output_path, "PNG", optimize=True)
                img_b64 = base64.b64encode(output_path.read_bytes()).decode()
                logger.info(f"Logo overlay applied to graphic {job_id}")
        except Exception as logo_err:
            logger.warning(f"Logo overlay failed (non-fatal): {logo_err}")
        # ─────────────────────────────────────────────────────────────────────

        image_url = f"/outputs/graphics/{output_filename}"
        update_graphic_job("completed", "Done", 100, image_url=image_url, image_b64=img_b64)
        logger.info(f"Graphic job {job_id} completed: {output_path}")

    except Exception as e:
        logger.error(f"Graphic job {job_id} failed: {e}")
        update_graphic_job("failed", error=str(e))


@app.post("/generate-graphic", response_model=GraphicGenerateResponse)
async def generate_graphic_endpoint(req: GraphicGenerateRequest, background_tasks: BackgroundTasks):
    """Start an async graphic generation job."""
    job_id = str(uuid.uuid4())
    GRAPHIC_JOB_STORE[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "content_type": req.content_type,
        "size_ratio": req.size_ratio,
        "user_prompt": req.user_prompt,
        "step": "Queued",
        "progress": 0,
        "error": None,
        "image_url": None,
        "image_b64": None,
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(_run_graphic_pipeline, job_id, req)
    return GraphicGenerateResponse(job_id=job_id, status="queued", message="Graphic generation started")


@app.get("/graphic-status/{job_id}", response_model=GraphicStatusResponse)
def get_graphic_status(job_id: str):
    """Get the status of a graphic generation job."""
    job = GRAPHIC_JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Graphic job not found")
    return GraphicStatusResponse(**{k: job.get(k) for k in GraphicStatusResponse.model_fields})


@app.get("/graphic-jobs")
def list_graphic_jobs(client_id: Optional[str] = None):
    """List all graphic generation jobs, newest first."""
    jobs = list(GRAPHIC_JOB_STORE.values())
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    # Strip b64 from list view to keep response small
    return [
        {k: v for k, v in j.items() if k != "image_b64"}
        for j in jobs
    ]


@app.get("/graphic-sizes")
def list_graphic_sizes():
    """Return available size presets with labels."""
    return [
        {"ratio": ratio, "width": info["width"], "height": info["height"], "label": info["label"]}
        for ratio, info in GRAPHIC_SIZE_PRESETS.items()
    ]


@app.get("/graphic-content-types")
def list_graphic_content_types():
    """Return available content types."""
    return [
        {"id": "tip_card",     "label": "Tip Card",     "description": "Educational tip or fact with Unity"},
        {"id": "before_after", "label": "Before / After","description": "Split before/after project reveal"},
        {"id": "carousel",     "label": "Carousel Slide","description": "Multi-slide series (e.g. 5 tips)"},
        {"id": "testimonial",  "label": "Testimonial",  "description": "Customer quote with star rating"},
        {"id": "promotional",  "label": "Promotional",  "description": "Offer, announcement, or seasonal promo"},
    ]

# ─── Root redirect ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Unity Video Producer API", "docs": "/docs", "app": "/app"}
