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
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests as http_requests
from PIL import Image as PILImage
import io

from pipeline.orchestrator import run_pipeline, JOB_STORE, JobStatus, update_job, KEYFRAME_APPROVAL_EVENTS, KEYFRAME_APPROVAL_DECISIONS
from pipeline.client_config import get_client, list_clients, reload_clients
from pipeline.script_writer import generate_script
from pipeline._keyframe_registry import set_registry
from credential_store import credential_statuses, get_credential, initialize_store, store_credential
from media_library import (
    clear_assignment,
    delete_asset as delete_media_asset,
    get_asset_path as get_media_asset_path,
    initialize_media_library,
    list_assets as list_media_assets,
    list_assignments as list_media_assignments,
    save_assignment as save_media_assignment,
    save_upload as save_media_upload,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unity Video Producer", version="1.0.0")
initialize_store()
initialize_media_library()

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
    output_ratio: str = "9:16"  # "1:1" | "4:5" | "9:16" | "16:9"
    client_id: str = "unified"  # multi-tenant: which client config to use


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ScriptPreviewRequest(BaseModel):
    topic: str
    format: str
    length: str
    client_id: str = "unified"


class ScriptPreviewResponse(BaseModel):
    script: str
    topic: str
    format: str
    length: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    step: Optional[str] = None
    progress: Optional[int] = None  # 0–100
    error: Optional[str] = None
    video_url: Optional[str] = None


class SettingsLoginRequest(BaseModel):
    password: str


class CredentialUpdateRequest(BaseModel):
    api_key: str


class MediaAssignmentRequest(BaseModel):
    scene_asset_id: str
    audio_asset_id: Optional[str] = None


SETTINGS_SESSION_COOKIE = "uvp_settings_session"
SETTINGS_SESSIONS: dict[str, float] = {}
SETTINGS_SESSION_TTL_SECONDS = 8 * 60 * 60


def _require_settings_session(request: Request) -> None:
    import time
    token = request.cookies.get(SETTINGS_SESSION_COOKIE, "")
    expires_at = SETTINGS_SESSIONS.get(token, 0)
    if not token or expires_at <= time.time():
        if token:
            SETTINGS_SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Settings session required")


@app.post("/settings/session")
def create_settings_session(req: SettingsLoginRequest, response: Response):
    import hmac
    import secrets
    import time
    configured_password = os.environ.get("APP_PASSWORD", "")
    if not configured_password or not hmac.compare_digest(req.password, configured_password):
        raise HTTPException(status_code=401, detail="Invalid team password")
    token = secrets.token_urlsafe(32)
    SETTINGS_SESSIONS[token] = time.time() + SETTINGS_SESSION_TTL_SECONDS
    response.set_cookie(
        key=SETTINGS_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=SETTINGS_SESSION_TTL_SECONDS,
        path="/",
    )
    return {"status": "ok"}


@app.delete("/settings/session")
def delete_settings_session(request: Request, response: Response):
    token = request.cookies.get(SETTINGS_SESSION_COOKIE, "")
    if token:
        SETTINGS_SESSIONS.pop(token, None)
    response.delete_cookie(SETTINGS_SESSION_COOKIE, path="/")
    return {"status": "ok"}


@app.get("/settings/credentials")
def list_credential_settings(request: Request):
    _require_settings_session(request)
    return credential_statuses()


@app.put("/settings/credentials/{provider}")
def update_credential_setting(provider: str, req: CredentialUpdateRequest, request: Request):
    _require_settings_session(request)
    saved, message = store_credential(provider, req.api_key)
    if not saved:
        raise HTTPException(status_code=422, detail=message)
    return {"status": "saved", "label": provider, "message": message}


@app.get("/settings/media/assets")
def list_settings_media_assets(request: Request):
    _require_settings_session(request)
    return list_media_assets()


@app.post("/settings/media/assets")
async def upload_settings_media_asset(request: Request, file: UploadFile = File(...)):
    _require_settings_session(request)
    try:
        asset = save_media_upload(file.filename or "upload", file.content_type or "", await file.read())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return asset


@app.get("/settings/media/files/{asset_id}")
def serve_settings_media_asset(asset_id: str, request: Request):
    _require_settings_session(request)
    path = get_media_asset_path(asset_id)
    if not path:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return FileResponse(path)


@app.delete("/settings/media/assets/{asset_id}")
def delete_settings_media_asset(asset_id: str, request: Request):
    _require_settings_session(request)
    if not delete_media_asset(asset_id):
        raise HTTPException(status_code=404, detail="Media asset not found")
    return {"status": "deleted"}


@app.get("/settings/media/assignments")
def list_settings_media_assignments(request: Request):
    _require_settings_session(request)
    return list_media_assignments()


@app.put("/settings/media/assignments/{slot}/{output_ratio}")
def update_settings_media_assignment(slot: str, output_ratio: str, req: MediaAssignmentRequest, request: Request):
    _require_settings_session(request)
    try:
        return save_media_assignment(slot, output_ratio, req.scene_asset_id, req.audio_asset_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.delete("/settings/media/assignments/{slot}/{output_ratio}")
def clear_settings_media_assignment(slot: str, output_ratio: str, request: Request):
    _require_settings_session(request)
    try:
        clear_assignment(slot, output_ratio)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {"status": "cleared"}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "Unity Video Producer"}


@app.post("/generate-script", response_model=ScriptPreviewResponse)
async def generate_script_preview(req: ScriptPreviewRequest):
    """Generate a reviewable script draft without creating a video job."""
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="Topic is required")
    try:
        script = await asyncio.to_thread(
            generate_script, topic, req.format, req.length, req.client_id
        )
    except Exception:
        logger.exception("Script preview generation failed for topic=%r", topic)
        raise HTTPException(
            status_code=502,
            detail="Unable to generate a script draft. Please try again.",
        )
    if not script:
        raise HTTPException(
            status_code=502,
            detail="The script generator returned an empty draft. Please try again.",
        )
    return ScriptPreviewResponse(
        script=script,
        topic=topic,
        format=req.format,
        length=req.length,
    )


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
        output_ratio=req.output_ratio,
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
            "output_ratio": j.output_ratio,
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
        output_ratio=job.original_output_ratio or job.output_ratio,
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
        output_ratio=job.original_output_ratio or job.output_ratio,
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
    openai_client = OpenAI(api_key=get_credential("openai"))
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
    # Frontend sends { description }. Keep scene_description + label optional
    # for backward compatibility with older callers.
    description: str = ""           # plain English description of the scene
    scene_description: str = ""     # legacy alias
    label: str = ""                 # optional human-readable name

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
    """Generate a new Unity keyframe using GPT Image (gpt-image-1) with the 4 library
    reference keyframes — IDENTICAL pipeline to generate_new_keyframe (video build),
    generate-social-image, and the graphics module."""
    openai_api_key = get_credential("openai")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Accept either `description` (current frontend) or `scene_description` (legacy)
    scene = (req.description or req.scene_description or "").strip()
    if not scene:
        raise HTTPException(status_code=400, detail="A scene description is required")

    # Verbatim keyframe prompt (matches generate_new_keyframe in keyframe.py)
    prompt = (
        f"Smooth modern 3D animation style. Unity the golden retriever mascot - "
        f"golden yellow fur, red bandana with orange house icon, brown leather tool belt "
        f"with wrench and hammer - {scene}. "
        f"3/4 angle showing front AND side, fluffy golden tail clearly visible. "
        f"Friendly energetic expression, mouth slightly open. "
        f"Soft warm rim lighting, professional branded video style. Full body head to paws."
    )

    # Same 4 library reference keyframes
    priority_refs = ["front_neutral.png", "doors.png", "windows.png", "walking_street.png"]
    ref_files = []
    for ref in priority_refs:
        p = KEYFRAMES_DIR / ref
        if not p.exists():
            p = REFERENCES_DIR / ref
        if p.exists():
            ref_files.append(p)
    if not ref_files:
        raise HTTPException(status_code=500, detail="No reference keyframe images found on server")

    files = []
    for rp in ref_files[:4]:
        files.append(("image[]", (rp.name, open(rp, "rb"), "image/png")))
    try:
        gpt_response = http_requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            data={"model": "gpt-image-1", "prompt": prompt, "n": "1", "size": "1024x1024"},
            files=files,
            timeout=120,
        )
    finally:
        for _, (_, fh, _) in files:
            fh.close()
    if gpt_response.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"GPT Image error ({gpt_response.status_code}): {gpt_response.text[:300]}")

    item = gpt_response.json()["data"][0]
    if "b64_json" in item and item["b64_json"]:
        img_b64 = item["b64_json"]
    elif "url" in item and item["url"]:
        img_b64 = base64.b64encode(http_requests.get(item["url"], timeout=60).content).decode()
    else:
        raise HTTPException(status_code=500, detail="No image data in GPT Image response")

    # Save to a temp file so the save step can retrieve it
    temp_filename = f"temp_{uuid.uuid4().hex[:8]}.png"
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = KEYFRAMES_DIR / temp_filename
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
    user_prompt: str            # scene description — what the visual should show
    headline: Optional[str] = None   # 2–5 word bold headline (composited in post)
    cta_text: Optional[str] = None   # CTA pill text e.g. "Get a Free Quote" (composited in post)
    subtext: Optional[str] = None    # optional 1 line below headline (≤6 words)
    client_id: str = "unified"
    total_slides: int = 1       # for carousel: total number of slides
    slide_num: int = 1          # for carousel: which slide this is
    uploaded_image_path: Optional[str] = None  # server path of user-uploaded photo

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

# ── Visual-only scene prompts (NO text, NO logo — composited in post) ──────────
# Key rule: AI generates the SCENE ONLY. All text, headline, CTA, and logo
# are stamped on top by the compositor.py post-processing step.
GRAPHIC_CONTENT_PROMPTS = {
    "tip_card": """Generate a clean visual scene for a home improvement social media graphic.
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt with wrench and hammer, floppy ears, fluffy tail, friendly smile) is featured prominently, pointing or gesturing confidently toward the right side of the frame.
Background: a clean, well-lit suburban home interior or exterior relevant to the topic.
DO NOT include any text, words, labels, logos, watermarks, or UI elements in the image.
Leave the top 18% and bottom 18% of the frame visually simple — no important subject matter there, as text overlays will be placed in those zones.
High-quality smooth 3D Pixar-style illustration. Warm natural lighting. Professional composition.
Scene topic: {user_prompt}""",

    "before_after": """Generate a clean split visual scene for a before/after home improvement social media graphic.
Left half of the image: older, worn, or dated version of the home feature (dull colors, aged materials).
Right half of the image: new, renovated, bright version of the same feature (fresh, modern, clean).
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) stands at the center dividing line giving a thumbs up with a proud expression.
DO NOT include any text, words, labels, logos, watermarks, or UI elements in the image — no "BEFORE" or "AFTER" labels.
Leave the top 18% and bottom 18% of the frame visually simple — text overlays will be placed there.
High-quality smooth 3D Pixar-style illustration. Professional home improvement visual.
Scene topic: {user_prompt}""",

    "carousel": """Generate a clean visual scene for slide {slide_num} of {total_slides} in a home improvement carousel.
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) appears in a helpful, guiding pose relevant to the topic.
Background: clean, well-lit home setting relevant to the slide topic.
DO NOT include any text, words, labels, slide numbers, logos, or UI elements in the image.
Leave the top 18% and bottom 18% of the frame visually simple — text overlays will be placed there.
High-quality smooth 3D Pixar-style illustration. Warm natural lighting.
Scene topic: {user_prompt}""",

    "testimonial": """Generate a clean visual scene for a customer testimonial social media graphic.
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) sits happily in the lower-right corner giving a thumbs up or smiling warmly.
Background: a clean, warm, neutral or softly blurred home interior — inviting and trustworthy.
DO NOT include any text, quote marks, star ratings, names, logos, or UI elements in the image.
Leave the top 18% and bottom 18% of the frame visually simple — text overlays will be placed there.
High-quality smooth 3D Pixar-style illustration. Soft warm lighting. Clean composition.
Scene mood: {user_prompt}""",

    "promotional": """Generate a clean high-energy visual scene for a promotional home improvement social media graphic.
Unity the golden retriever mascot (golden yellow fur, red triangular bandana with small house icon, brown leather tool belt) is featured prominently looking excited and energetic, arms raised or pointing forward.
Background: a dynamic, vibrant home exterior or renovation scene with energy and movement.
DO NOT include any text, words, labels, logos, watermarks, price tags, or UI elements in the image.
Leave the top 18% and bottom 18% of the frame visually simple — text overlays will be placed there.
High-quality smooth 3D Pixar-style illustration. Bold warm lighting. High-energy composition.
Scene topic: {user_prompt}""",
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
        # Build prompt from content-type template
        scene_prompt = _build_graphic_prompt(
            req.content_type, req.user_prompt, req.size_ratio,
            req.slide_num, req.total_slides
        )
        # Determine orientation label for the prompt
        size_preset = GRAPHIC_SIZE_PRESETS.get(req.size_ratio, GRAPHIC_SIZE_PRESETS["1:1"])
        w, h = size_preset["width"], size_preset["height"]
        if w > h:
            orientation = "landscape orientation (wider than tall)"
        elif h > w:
            orientation = "portrait orientation (taller than wide)"
        else:
            orientation = "square orientation"
        # Full prompt — same structure as social image pipeline for 3D Pixar consistency
        prompt = (
            f"Smooth modern 3D animation style. Unity the golden retriever mascot — "
            f"golden yellow fur, red bandana with orange house icon, brown leather tool belt "
            f"with wrench and hammer — {scene_prompt}. "
            f"3/4 angle showing front AND side, fluffy golden tail clearly visible. "
            f"Friendly energetic expression, mouth slightly open. "
            f"Unity stands about 4.5 feet tall on his hind legs — roughly chest height to an adult, clearly shorter than a standard door — so scale all surrounding objects (doors, windows, cars) realistically against this height. "
            f"Soft warm rim lighting, professional branded video style. Full body head to paws. "
            f"Leave the top 18% and bottom 18% of the frame visually simple — text overlays will be placed there. "
            f"No text, no logos."
        )
        # If user uploaded a reference photo, instruct the model to incorporate it
        if uploaded_image_path and Path(uploaded_image_path).exists():
            prompt += (
                " The user has provided a reference photo (first image in the reference set). "
                "Incorporate the setting, colors, materials, and subject matter from that photo "
                "into the background or scene. Blend it naturally with the Unity mascot character."
            )
            logger.info(f"[graphics] Photo reference added to prompt for job {job_id}")
        # Load the 4 keyframe reference images — same refs used by video pipeline
        priority_refs = [
            "front_neutral.png",
            "doors.png",
            "windows.png",
            "walking_street.png",
        ]
        ref_files = []
        for ref in priority_refs:
            p = KEYFRAMES_DIR / ref
            if not p.exists():
                p = REFERENCES_DIR / ref
            if p.exists():
                ref_files.append(p)
        if not ref_files:
            raise Exception("No reference keyframe images found on server")
        # Map size ratio to nearest GPT Image supported size
        gpt_size_map = {
            "1:1":  "1024x1024",
            "4:5":  "1024x1024",
            "9:16": "1024x1536",
            "16:9": "1536x1024",
        }
        gpt_size = gpt_size_map.get(req.size_ratio, "1024x1024")
        # Output path
        output_filename = f"graphic_{job_id[:8]}.png"
        output_path = GRAPHICS_DIR / output_filename
        openai_api_key = get_credential("openai")
        if not openai_api_key:
            raise Exception("OPENAI_API_KEY not configured")

        # ── OPTION B: Two-pass generation when user uploaded a photo ─────────
        stylized_bg_path = None
        if uploaded_image_path and Path(uploaded_image_path).exists():
            update_graphic_job("running", "Pass 1 — Converting photo to 3D animated scene...", 30)
            logger.info(f"[graphics] Pass 1: stylizing uploaded photo for job {job_id}")
            up = Path(uploaded_image_path)
            mime = "image/jpeg" if up.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            bg_prompt = (
                "Convert this photo into a clean, smooth Pixar-style 3D animated background scene. "
                "Keep the exact same room layout, furniture arrangement, and spatial depth. "
                "Match the lighting direction and color temperature of the original photo. "
                "Render everything in warm, soft 3D animation style — same quality as Pixar or Disney films. "
                "Do NOT add any characters, people, animals, or text. "
                "The scene should be empty and ready for a 3D animated character to be placed in it. "
                "Preserve the perspective and camera angle of the original photo exactly."
            )
            pass1_files = [("image[]", (up.name, open(up, "rb"), mime))]
            try:
                pass1_resp = http_requests.post(
                    "https://api.openai.com/v1/images/edits",
                    headers={"Authorization": f"Bearer {openai_api_key}"},
                    data={"model": "gpt-image-1", "prompt": bg_prompt, "n": "1", "size": gpt_size},
                    files=pass1_files,
                    timeout=120,
                )
            finally:
                for _, (_, fh, _) in pass1_files:
                    fh.close()
            if pass1_resp.status_code not in (200, 201):
                logger.warning(f"[graphics] Pass 1 failed ({pass1_resp.status_code}), falling back to single-pass")
            else:
                p1_item = pass1_resp.json()["data"][0]
                if "b64_json" in p1_item and p1_item["b64_json"]:
                    p1_bytes = base64.b64decode(p1_item["b64_json"])
                elif "url" in p1_item and p1_item["url"]:
                    p1_bytes = http_requests.get(p1_item["url"], timeout=60).content
                else:
                    p1_bytes = None
                if p1_bytes:
                    stylized_bg_path = Path(uploaded_image_path).parent / f"stylized_{job_id[:8]}.png"
                    stylized_bg_path.write_bytes(p1_bytes)
                    logger.info(f"[graphics] Pass 1 complete: stylized bg saved to {stylized_bg_path}")
        # ─────────────────────────────────────────────────────────────────────

        update_graphic_job("running", "Pass 2 — Placing Unity in the scene..." if stylized_bg_path else "Generating graphic with GPT Image...", 55)
        logger.info(f"[graphics] Pass 2: generating Unity graphic for job {job_id}")

        files = []
        if stylized_bg_path and stylized_bg_path.exists():
            # Pass 2: stylized background first (sets the scene), then Unity keyframe refs
            files.append(("image[]", (stylized_bg_path.name, open(stylized_bg_path, "rb"), "image/png")))
            keyframe_limit = 3
            # Enhance prompt to place Unity naturally in the stylized scene
            prompt += (
                " The first reference image is a stylized 3D animated version of the customer's actual room/project. "
                "Place Unity naturally inside that exact scene — matching the lighting, perspective, and depth of the room. "
                "Unity should appear to be physically standing in that space, not pasted on top of it."
            )
        else:
            keyframe_limit = 4
        for rp in ref_files[:keyframe_limit]:
            files.append(("image[]", (rp.name, open(rp, "rb"), "image/png")))
        try:
            gpt_response = http_requests.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {openai_api_key}"},
                data={"model": "gpt-image-1", "prompt": prompt, "n": "1", "size": gpt_size},
                files=files,
                timeout=120,
            )
        finally:
            for _, (_, fh, _) in files:
                fh.close()
        if gpt_response.status_code not in (200, 201):
            raise Exception(f"GPT Image error ({gpt_response.status_code}): {gpt_response.text[:300]}")
        update_graphic_job("running", "Saving graphic...", 80)
        item = gpt_response.json()["data"][0]
        if "b64_json" in item and item["b64_json"]:
            img_b64 = item["b64_json"]
        elif "url" in item and item["url"]:
            img_b64 = base64.b64encode(http_requests.get(item["url"], timeout=60).content).decode()
        else:
            raise Exception("No image data in GPT Image response")
        output_path.write_bytes(base64.b64decode(img_b64))

        # ── Ad Compositor: headline + CTA pill + logo + layout zones ─────────
        update_graphic_job("running", "Compositing ad layout...", 88)
        try:
            from pipeline.client_config import get_asset_path as _get_asset_path
            from pipeline.compositor import composite_ad, DEFAULT_HEADLINE, DEFAULT_CTA

            logo_path = _get_asset_path(req.client_id, "logo")

            # Resolve headline — use user-supplied value or smart default
            headline = req.headline or DEFAULT_HEADLINE.get(req.content_type, "Home Improvement Tips")
            # CTA: if user explicitly passed an empty string, skip the CTA pill entirely.
            # Only fall back to DEFAULT_CTA when the field was not sent at all (None).
            if req.cta_text is None:
                cta = DEFAULT_CTA.get(req.content_type, "Get a Free Quote")
            else:
                cta = req.cta_text.strip() or None  # empty string → None → no pill
            subtext  = req.subtext or None

            composite_ad(
                image_path=str(output_path),
                headline=headline,
                cta_text=cta,
                logo_path=str(logo_path) if logo_path else None,
                output_path=str(output_path),
                content_type=req.content_type,
                subtext=subtext,
            )

            with open(output_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            logger.info(f"[graphics] Ad compositor applied to {output_filename} (headline='{headline}', cta='{cta}')")
        except Exception as comp_err:
            logger.warning(f"[graphics] Compositor failed (non-fatal): {comp_err}")
        # ─────────────────────────────────────────────────────────────────────

        image_url = f"/outputs/graphics/{output_filename}"
        update_graphic_job("completed", "Done", 100, image_url=image_url, image_b64=img_b64)
        logger.info(f"Graphic job {job_id} completed: {output_path}")

    except Exception as e:
        logger.error(f"Graphic job {job_id} failed: {e}")
        update_graphic_job("failed", error=str(e))


@app.post("/upload-graphic-photo")
async def upload_graphic_photo(photo: UploadFile = File(...)):
    """Accept a user-uploaded photo and save it to a temp location for use in graphic generation."""
    import uuid as _uuid
    allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    if photo.content_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {photo.content_type}")
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in (photo.filename or "") else "jpg"
    filename = f"upload_{_uuid.uuid4().hex[:8]}.{ext}"
    upload_dir = Path(__file__).parent / "assets" / "graphic_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / filename
    content = await photo.read()
    dest.write_bytes(content)
    logger.info(f"[graphics] Uploaded photo saved: {dest} ({len(content)} bytes)")
    return {"path": str(dest), "filename": filename}

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
    background_tasks.add_task(_run_graphic_pipeline, job_id, req, req.uploaded_image_path)
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


# ─── Social Media Image Generation ───────────────────────────────────────────

SOCIAL_MEDIA_DIR = Path(__file__).parent / "assets" / "social_media"
SOCIAL_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Serve social media images statically
app.mount("/social-media", StaticFiles(directory=str(SOCIAL_MEDIA_DIR)), name="social_media")

SOCIAL_SIZE_PRESETS = {
    "1:1":  {"width": 1024, "height": 1024,  "label": "Square (1:1) — Instagram / Facebook Feed"},
    "4:5":  {"width": 1024, "height": 1280,  "label": "Portrait (4:5) — Instagram Feed"},
    "9:16": {"width": 1024, "height": 1792,  "label": "Vertical (9:16) — Stories / Reels / TikTok"},
    "16:9": {"width": 1792, "height": 1024,  "label": "Landscape (16:9) — Facebook / YouTube Cover"},
    "4:3":  {"width": 1024, "height": 768,   "label": "Landscape (4:3) — Facebook Post"},
}


class SocialImageGenerateRequest(BaseModel):
    scene_description: str          # what Unity is doing / environment
    aspect_ratio: str = "1:1"       # "1:1" | "4:5" | "9:16" | "16:9" | "4:3"
    client_id: str = "unified"


class SocialImageGenerateResponse(BaseModel):
    image_b64: str       # base64 PNG for preview
    temp_filename: str   # server-side temp file for save step


class SocialImageSaveRequest(BaseModel):
    temp_filename: str
    label: str           # human-readable name e.g. "Unity Cleaning Window"
    filename: str        # e.g. "unity_cleaning_window.png"
    port_to: str = ""    # "library" | "graphics" | "" (just save to social media)


class SocialImageSaveResponse(BaseModel):
    filename: str
    label: str
    url: str
    ported_to: str
    message: str


@app.get("/social-media-sizes")
def list_social_media_sizes():
    """Return available aspect ratio presets for social media image generation."""
    return [
        {"ratio": ratio, "width": info["width"], "height": info["height"], "label": info["label"]}
        for ratio, info in SOCIAL_SIZE_PRESETS.items()
    ]


@app.post("/generate-social-image", response_model=SocialImageGenerateResponse)
async def generate_social_image(req: SocialImageGenerateRequest):
    """Generate a clean Unity image (no text, no logo) at the requested aspect ratio."""
    size = SOCIAL_SIZE_PRESETS.get(req.aspect_ratio, SOCIAL_SIZE_PRESETS["1:1"])
    w, h = size["width"], size["height"]

    # Determine orientation label for the prompt
    if w > h:
        orientation = "landscape orientation (wider than tall)"
    elif h > w:
        orientation = "portrait orientation (taller than wide)"
    else:
        orientation = "square orientation"

    prompt = (
        f"Smooth modern 3D animation style. Unity the golden retriever mascot — "
        f"golden yellow fur, red bandana with orange house icon, brown leather tool belt "
        f"with wrench and hammer — {req.scene_description}. "
        f"3/4 angle showing front AND side, fluffy golden tail clearly visible. "
        f"Friendly energetic expression, mouth slightly open. "
        f"Unity stands about 4.5 feet tall on his hind legs — roughly chest height to an adult, clearly shorter than a standard door — so scale all surrounding objects (doors, windows, cars) realistically against this height. "
        f"Soft warm rim lighting, professional branded video style. Full body head to paws. "
        f"No text, no logos."
    )
    # Load reference images — they live in KEYFRAMES_DIR (front_neutral, thumbs_up, etc.)
    priority_refs = [
        "front_neutral.png",
        "doors.png",
        "windows.png",
        "walking_street.png",
    ]
    ref_files = []
    for ref in priority_refs:
        # Check keyframes dir first (where they actually live), fallback to references dir
        p = KEYFRAMES_DIR / ref
        if not p.exists():
            p = REFERENCES_DIR / ref
        if p.exists():
            ref_files.append(p)

    if not ref_files:
        raise HTTPException(status_code=500, detail="No reference images found on server")

    # Use GPT Image (gpt-image-1) via images/edits with reference images for 3D Pixar-style consistency
    openai_api_key = get_credential("openai")
    if not openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    # Map aspect ratio to nearest supported GPT Image size
    size_map = {
        "1:1":  "1024x1024",
        "4:5":  "1024x1024",   # closest square
        "9:16": "1024x1536",
        "16:9": "1536x1024",
        "4:3":  "1536x1024",   # closest landscape
    }
    gpt_size = size_map.get(req.aspect_ratio, "1024x1024")

    # Build multipart files list — send up to 4 reference images
    files = []
    for rp in ref_files[:4]:
        files.append(("image[]", (rp.name, open(rp, "rb"), "image/png")))
    try:
        gpt_response = http_requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            data={"model": "gpt-image-1", "prompt": prompt, "n": "1", "size": gpt_size},
            files=files,
            timeout=120,
        )
    finally:
        for _, (_, fh, _) in files:
            fh.close()

    if gpt_response.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"GPT Image error ({gpt_response.status_code}): {gpt_response.text[:300]}")

    item = gpt_response.json()["data"][0]
    if "b64_json" in item and item["b64_json"]:
        img_b64 = item["b64_json"]
    elif "url" in item and item["url"]:
        img_b64 = base64.b64encode(http_requests.get(item["url"], timeout=60).content).decode()
    else:
        raise HTTPException(status_code=500, detail="No image data in GPT Image response")

    # Save to temp file in social_media dir
    temp_filename = f"temp_{uuid.uuid4().hex[:8]}.png"
    temp_path = SOCIAL_MEDIA_DIR / temp_filename
    with open(temp_path, "wb") as f:
        f.write(base64.b64decode(img_b64))

    return SocialImageGenerateResponse(image_b64=img_b64, temp_filename=temp_filename)


@app.post("/save-social-image", response_model=SocialImageSaveResponse)
def save_social_image(req: SocialImageSaveRequest):
    """Save a generated social media image. Optionally port it to the keyframe library or graphics."""
    safe_name = re.sub(r"[^a-z0-9_]", "", req.filename.lower().replace(" ", "_").replace("-", "_"))
    if not safe_name.endswith(".png"):
        safe_name += ".png"

    import shutil
    source_path = SOCIAL_MEDIA_DIR / req.temp_filename
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Image not found — please regenerate")

    # Save permanently to social media folder
    final_path = SOCIAL_MEDIA_DIR / safe_name
    # Only copy if source and destination are different files (avoid SameFileError on re-save)
    if source_path.resolve() != final_path.resolve():
        shutil.copy2(str(source_path), str(final_path))
        # Only delete if it was a temp file (preserve permanent files for subsequent saves/ports)
        if req.temp_filename.startswith("temp_"):
            source_path.unlink(missing_ok=True)

    ported_to = ""

    # Port to keyframe library if requested
    if req.port_to == "library":
        kf_path = KEYFRAMES_DIR / safe_name
        shutil.copy2(str(final_path), str(kf_path))
        KEYFRAME_META[safe_name] = {
            "label": req.label,
            "tags": ["social_media", "custom"],
            "category": "social_media",
        }
        ported_to = "library"

    # Port to graphics: save to social media dir (graphics picks it up via user_prompt/scene)
    # For graphics porting we just return the URL so the frontend can pre-fill the Graphics form
    if req.port_to == "graphics":
        ported_to = "graphics"

    return SocialImageSaveResponse(
        filename=safe_name,
        label=req.label,
        url=f"/social-media/{safe_name}",
        ported_to=ported_to,
        message=f"Image '{req.label}' saved successfully"
        + (f" and ported to {ported_to}" if ported_to else ""),
    )


@app.get("/social-media-images")
def list_social_media_images():
    """List all saved social media images."""
    images = []
    for f in sorted(SOCIAL_MEDIA_DIR.glob("*.png")):
        if f.name.startswith("temp_"):
            continue
        images.append({
            "filename": f.name,
            "label": f.stem.replace("_", " ").title(),
            "url": f"/social-media/{f.name}",
            "size": f.stat().st_size,
        })
    return images

@app.delete("/social-media-images/{filename}")
def delete_social_media_image(filename: str):
    """Delete a saved social media gallery image."""
    # Sanitize filename — no path traversal
    safe_name = Path(filename).name
    if not safe_name.endswith(".png") or safe_name.startswith("temp_"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    img_path = SOCIAL_MEDIA_DIR / safe_name
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    img_path.unlink()
    return {"message": f"Image '{safe_name}' deleted"}
