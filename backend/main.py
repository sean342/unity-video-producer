"""
Unity Video Producer — FastAPI Backend
Async job queue for AI video generation pipeline.
"""
import os
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.orchestrator import run_pipeline, JOB_STORE, JobStatus

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
    format: str  # "myth_or_fact" | "quick_tip" | "did_you_know"
    length: str  # "8s" | "15s" | "20s"
    custom_script: Optional[str] = None  # override auto-generated script


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
def list_jobs():
    """List all jobs (most recent first)."""
    jobs = list(JOB_STORE.values())
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
            "created_at": j.created_at,
            "video_url": j.video_url,
        }
        for j in jobs[:50]  # last 50 jobs
    ]


# ─── Root redirect ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Unity Video Producer API", "docs": "/docs", "app": "/app"}
