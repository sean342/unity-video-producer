"""
Pipeline Orchestrator — manages the full Unity video generation workflow.
Steps:
  1. Script generation (GPT or template)
  2. Voice (ElevenLabs)
  3. Keyframe (Leonardo.ai)
  4. Animation + lip sync (Kling Avatar v2 via fal.ai)
  5. Captions (Pillow PNG overlays)
  6. Assembly (FFmpeg)
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from .script_writer import generate_script
from .voice import generate_voice
from .keyframe import generate_keyframe
from .animation import generate_animation
from .captions import render_captions
from .assembler import assemble_video

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# In-memory job store (replace with Redis/DB for production)
JOB_STORE: Dict[str, "JobStatus"] = {}


@dataclass
class JobStatus:
    job_id: str
    status: str = "queued"       # queued | running | complete | failed
    step: str = "Queued"
    progress: int = 0
    error: Optional[str] = None
    video_url: Optional[str] = None
    topic: str = ""
    format: str = ""
    length: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def update_job(job_id: str, **kwargs):
    job = JOB_STORE.get(job_id)
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)


async def run_pipeline(
    job_id: str,
    topic: str,
    format: str,
    length: str,
    custom_script: Optional[str] = None,
):
    """Run the full Unity video production pipeline asynchronously."""
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    update_job(job_id, status="running", topic=topic, format=format, length=length)

    try:
        # ── Step 1: Script ──────────────────────────────────────────────────
        update_job(job_id, step="Writing script", progress=5)
        if custom_script:
            script = custom_script
        else:
            script = await asyncio.to_thread(generate_script, topic, format, length)
        logger.info(f"[{job_id}] Script: {script}")

        # ── Step 2: Voice ───────────────────────────────────────────────────
        update_job(job_id, step="Generating voice (ElevenLabs)", progress=15)
        voice_path, timestamps = await asyncio.to_thread(generate_voice, script, job_dir)
        logger.info(f"[{job_id}] Voice: {voice_path}")

        # ── Step 3: Keyframe ────────────────────────────────────────────────
        update_job(job_id, step="Generating keyframe image (Leonardo.ai)", progress=28)
        keyframe_url = await asyncio.to_thread(generate_keyframe, topic, format, job_dir)
        logger.info(f"[{job_id}] Keyframe URL: {keyframe_url}")

        # ── Step 4: Animation ───────────────────────────────────────────────
        update_job(job_id, step="Animating Unity (Kling Avatar v2 — ~4 min)", progress=35)
        raw_video_path = await asyncio.to_thread(
            generate_animation, keyframe_url, voice_path, topic, job_dir
        )
        logger.info(f"[{job_id}] Raw video: {raw_video_path}")

        # ── Step 5: Captions ────────────────────────────────────────────────
        update_job(job_id, step="Rendering captions", progress=80)
        caption_manifest = await asyncio.to_thread(render_captions, timestamps, job_dir)
        logger.info(f"[{job_id}] Captions: {len(caption_manifest)} lines")

        # ── Step 6: Assembly ────────────────────────────────────────────────
        update_job(job_id, step="Assembling final video (FFmpeg)", progress=90)
        final_path = OUTPUTS_DIR / f"{job_id}.mp4"
        await asyncio.to_thread(assemble_video, raw_video_path, caption_manifest, final_path)
        logger.info(f"[{job_id}] Final: {final_path}")

        # ── Done ─────────────────────────────────────────────────────────────
        update_job(
            job_id,
            status="complete",
            step="Complete",
            progress=100,
            video_url=f"/outputs/{job_id}.mp4",
        )
        logger.info(f"[{job_id}] ✓ Pipeline complete")

    except Exception as e:
        logger.exception(f"[{job_id}] Pipeline failed: {e}")
        update_job(job_id, status="failed", step="Failed", error=str(e))
