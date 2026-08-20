"""
Pipeline Orchestrator — manages the full Unity video generation workflow.
Steps:
  1. Script generation (GPT or template)
  2. Voice (ElevenLabs)
  3. Keyframe (Leonardo.ai)
  4. Animation + lip sync (Kling Avatar v2 via fal.ai)
  5. Captions (Pillow PNG overlays)
  6. Assembly (FFmpeg)

Job storage is persisted to disk (jobs.json) so history survives service restarts.
"""
import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from .script_writer import generate_script
from .voice import generate_voice
from .keyframe import generate_keyframe
from .animation import generate_animation
from .captions import render_captions
from .assembler import assemble_video
from .comedy_analyzer import analyze_comedy_script, resolve_cue_offsets
from .client_config import get_client

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

JOBS_FILE = Path(__file__).parent.parent / "jobs.json"

# In-memory job store — loaded from disk on startup
JOB_STORE: Dict[str, "JobStatus"] = {}
_store_lock = threading.Lock()

# Per-job asyncio Events for keyframe approval pausing
# Maps job_id -> asyncio.Event (set when user approves or regenerates)
KEYFRAME_APPROVAL_EVENTS: Dict[str, asyncio.Event] = {}
# Maps job_id -> "approved" | "regenerate"
KEYFRAME_APPROVAL_DECISIONS: Dict[str, str] = {}


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
    output_ratio: str = "9:16"
    client_id: str = "unified"   # multi-tenant: which client this job belongs to
    script: Optional[str] = None         # final script used (auto or custom)
    keyframe_url: Optional[str] = None   # URL of keyframe used in animation
    keyframe_label: Optional[str] = None # human-readable keyframe label
    # retry support — original params stored so failed jobs can be re-queued
    original_topic: Optional[str] = None
    original_format: Optional[str] = None
    original_length: Optional[str] = None
    original_output_ratio: Optional[str] = None
    original_custom_script: Optional[str] = None
    original_keyframe_override: Optional[str] = None
    original_keyframe_description: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def _save_jobs():
    """Persist JOB_STORE to disk atomically."""
    try:
        data = {job_id: asdict(job) for job_id, job in JOB_STORE.items()}
        tmp = JOBS_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(JOBS_FILE)
    except Exception as e:
        logger.warning(f"Failed to persist jobs.json: {e}")


def _load_jobs():
    """Load persisted jobs from disk into JOB_STORE on startup."""
    if not JOBS_FILE.exists():
        return
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
        for job_id, d in data.items():
            # Mark any jobs that were mid-run as failed (they were interrupted)
            if d.get("status") in ("queued", "running"):
                d["status"] = "failed"
                d["step"] = "Failed"
                d["error"] = "Service was restarted while this job was running."
            JOB_STORE[job_id] = JobStatus(**d)
        logger.info(f"Loaded {len(JOB_STORE)} jobs from disk")
    except Exception as e:
        logger.warning(f"Failed to load jobs.json: {e}")


def update_job(job_id: str, **kwargs):
    with _store_lock:
        job = JOB_STORE.get(job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)
            _save_jobs()


# Load persisted jobs when module is first imported
_load_jobs()


async def run_pipeline(
    job_id: str,
    topic: str,
    format: str,
    length: str,
    custom_script: Optional[str] = None,
    keyframe_override: Optional[str] = None,
    keyframe_description: Optional[str] = None,
    output_ratio: str = "9:16",
    client_id: str = "unified",
):
    """Run the full Unity video production pipeline asynchronously."""
    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    update_job(
        job_id,
        status="running",
        topic=topic,
        format=format,
        length=length,
        output_ratio=output_ratio,
        client_id=client_id,
        original_topic=topic,
        original_format=format,
        original_length=length,
        original_output_ratio=output_ratio,
        original_custom_script=custom_script,
        original_keyframe_override=keyframe_override,
        original_keyframe_description=keyframe_description,
    )

    try:
        # ── Step 1: Script ──────────────────────────────────────────────────
        update_job(job_id, step="Writing script", progress=5)
        if custom_script:
            script = custom_script
        else:
            script = await asyncio.to_thread(generate_script, topic, format, length)
        logger.info(f"[{job_id}] Script: {script}")
        update_job(job_id, script=script)

        # ── Step 1b: Comedy analysis (comedy format only) ───────────────────
        comedy_cues = None
        effective_format = format
        if format == "comedy" or (format == "custom" and custom_script):
            # For comedy format, always analyze; for custom scripts, check if it reads like comedy
            should_analyze = format == "comedy"
            if should_analyze:
                update_job(job_id, step="Analyzing comedy timing (GPT)", progress=10)
                comedy_analysis = await asyncio.to_thread(analyze_comedy_script, script)
                script = comedy_analysis.annotated_script  # use pause-annotated version
                comedy_cues = comedy_analysis.cues
                logger.info(f"[{job_id}] Comedy analysis: {len(comedy_cues)} cues, annotated script ready")

        # ── Step 2: Voice ───────────────────────────────────────────────────
        update_job(job_id, step="Generating voice (ElevenLabs)", progress=15)
        voice_path, timestamps = await asyncio.to_thread(generate_voice, script, job_dir, client_id)
        logger.info(f"[{job_id}] Voice: {voice_path}")

        # Resolve comedy cue offsets from actual word timestamps
        if comedy_cues and timestamps:
            word_ts = []
            # ElevenLabs alignment format: {characters, character_start_times_seconds, character_end_times_seconds}
            # Convert to word-level for cue matching
            chars = timestamps.get("characters", [])
            starts = timestamps.get("character_start_times_seconds", [])
            ends = timestamps.get("character_end_times_seconds", [])
            # Build word list from character timestamps
            current_word = ""
            word_start = 0.0
            for i, ch in enumerate(chars):
                end_t = ends[i] if i < len(ends) else 0
                start_t = starts[i] if i < len(starts) else 0
                if ch == " " or i == len(chars) - 1:
                    if ch != " ":
                        current_word += ch
                    if current_word.strip():
                        word_ts.append({"word": current_word.strip(), "start": word_start, "end": end_t})
                    current_word = ""
                    word_start = end_t
                else:
                    if not current_word:
                        word_start = start_t
                    current_word += ch
            comedy_cues = resolve_cue_offsets(comedy_cues, word_ts)
            logger.info(f"[{job_id}] Comedy cues resolved: {[(c.reaction_type, c.offset_seconds) for c in comedy_cues]}")

        # ── Step 3: Keyframe ────────────────────────────────────────────────
        if keyframe_override:
            update_job(job_id, step=f"Using selected keyframe: {keyframe_override}", progress=28)
            keyframe_url = await asyncio.to_thread(
                generate_keyframe, topic, format, job_dir, script, keyframe_override, client_id, "", output_ratio
            )
            kf_label = keyframe_override
            update_job(job_id, keyframe_url=keyframe_url, keyframe_label=kf_label)
        elif keyframe_description:
            # On-the-fly generation with approval loop
            attempt = 0
            keyframe_url = None
            current_description = keyframe_description
            while True:
                attempt += 1
                update_job(job_id, step=f"Generating new keyframe (attempt {attempt})...", progress=28)
                keyframe_url = await asyncio.to_thread(
                    generate_keyframe, topic, format, job_dir, script, "", client_id, current_description, output_ratio
                )
                logger.info(f"[{job_id}] Generated keyframe URL: {keyframe_url}")

                # Pause and wait for user approval
                approval_event = asyncio.Event()
                KEYFRAME_APPROVAL_EVENTS[job_id] = approval_event
                KEYFRAME_APPROVAL_DECISIONS.pop(job_id, None)
                update_job(
                    job_id,
                    status="waiting_keyframe_approval",
                    step="Waiting for keyframe approval",
                    progress=30,
                    keyframe_url=keyframe_url,
                    keyframe_label=f"generated (attempt {attempt})",
                )
                logger.info(f"[{job_id}] Waiting for keyframe approval...")

                # Wait up to 10 minutes for user decision
                try:
                    await asyncio.wait_for(approval_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    raise RuntimeError("Keyframe approval timed out after 10 minutes.")

                decision = KEYFRAME_APPROVAL_DECISIONS.get(job_id, "approved")
                KEYFRAME_APPROVAL_EVENTS.pop(job_id, None)
                KEYFRAME_APPROVAL_DECISIONS.pop(job_id, None)

                if decision == "approved":
                    logger.info(f"[{job_id}] Keyframe approved by user")
                    update_job(job_id, status="running", step="Keyframe approved — continuing...", progress=32)
                    break
                else:
                    # Regenerate — get new description if provided, else reuse
                    new_desc = KEYFRAME_APPROVAL_DECISIONS.get(f"{job_id}_new_description", current_description)
                    KEYFRAME_APPROVAL_DECISIONS.pop(f"{job_id}_new_description", None)
                    current_description = new_desc
                    logger.info(f"[{job_id}] Regenerating keyframe with description: {current_description}")
                    update_job(job_id, status="running")
        else:
            update_job(job_id, step="Selecting keyframe from library", progress=28)
            # Pass the full script so GPT can pick the best visual match
            keyframe_url = await asyncio.to_thread(generate_keyframe, topic, format, job_dir, script, "", client_id, "", output_ratio)
            kf_label = "auto"
            update_job(job_id, keyframe_url=keyframe_url, keyframe_label=kf_label)
        logger.info(f"[{job_id}] Keyframe URL: {keyframe_url}")

        # ── Step 4: Animation ───────────────────────────────────────────────
        update_job(job_id, step="Animating Unity (Kling Avatar v2 — ~4 min)", progress=35)
        # Pass keyframe_override so animation.py can find alt-angle variants (_alt1, _alt2)
        # for multi-angle camera cut transitions between chunks
        raw_video_path = await asyncio.to_thread(
            generate_animation, keyframe_url, voice_path, topic, job_dir, client_id,
            keyframe_override or ""
        )
        logger.info(f"[{job_id}] Raw video: {raw_video_path}")

        # ── Step 5: Captions ────────────────────────────────────────────────
        update_job(job_id, step="Rendering captions", progress=80)
        caption_manifest = await asyncio.to_thread(render_captions, timestamps, job_dir, output_ratio)
        logger.info(f"[{job_id}] Captions: {len(caption_manifest)} lines")

        # ── Step 6: Assembly ────────────────────────────────────────────────
        update_job(job_id, step="Assembling final video (FFmpeg)", progress=90)
        final_path = OUTPUTS_DIR / f"{job_id}.mp4"
        await asyncio.to_thread(assemble_video, raw_video_path, caption_manifest, final_path, comedy_cues, client_id, output_ratio)
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
