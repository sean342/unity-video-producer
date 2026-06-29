"""
Comedy Script Analyzer
Uses GPT-4.1-mini to:
  1. Annotate the script with ElevenLabs <break> pause tags for comedic timing
  2. Return a list of audience reaction cue points (laugh or applause) with
     estimated offsets in seconds from the start of the audio

The annotated script is passed to ElevenLabs instead of the raw script.
The cue points are passed to the assembler to mix in audience audio.
"""
import json
import logging
from dataclasses import dataclass
from typing import List
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class AudienceCue:
    offset_seconds: float   # seconds from start of voice audio to insert the reaction
    reaction_type: str      # "laugh" or "applause"
    duration_seconds: float # how long to play the clip (will be trimmed/faded)


@dataclass
class ComedyAnalysis:
    annotated_script: str       # script with <break time="Xs"/> tags for ElevenLabs
    cues: List[AudienceCue]     # audience reaction cue points


def analyze_comedy_script(script: str) -> ComedyAnalysis:
    """
    Analyze a comedy script and return:
    - An annotated version with pause markers for natural comedic delivery
    - Audience reaction cue points (laugh/applause) with timing estimates
    """
    client = OpenAI()

    prompt = f"""You are a comedy timing director for a short video featuring Unity, a golden retriever mascot.

Analyze this comedy script and return a JSON object with two fields:

1. "annotated_script": The script with ElevenLabs SSML <break time="Xs"/> tags inserted at the right moments for comedic timing. Rules:
   - Insert <break time="0.4s"/> after a setup line, just before the punchline
   - Insert <break time="0.3s"/> after a self-aware or ironic statement
   - Insert <break time="0.2s"/> for a brief beat mid-sentence if it adds timing
   - Do NOT add breaks at the very end — the audience reaction handles that
   - Keep the original words exactly — only add break tags, change nothing else

2. "cues": A JSON array of audience reaction objects. Each object has:
   - "reaction_type": "laugh" (mid-joke chuckle) or "applause" (end-of-bit celebration)
   - "after_line": The exact line of text that triggers the reaction (copy it verbatim)
   - "delay_seconds": How many seconds after that line ends before the reaction starts (0.1 to 0.5)
   - "duration_seconds": How long the reaction should play (laugh: 1.5–2.5s, applause: 2.5–3.5s)

Rules for cues:
   - Always end with an "applause" cue after the final line
   - Add a "laugh" cue after any clear punchline or funny observation mid-script
   - A short script (under 40 words) should have 1 laugh + 1 applause
   - A longer script can have 2 laughs + 1 applause
   - Never add more than 3 cues total

Script:
\"\"\"{script}\"\"\"

Respond with ONLY valid JSON — no markdown, no explanation."""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a comedy timing expert. Respond only with valid JSON."
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=600,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"[comedy] Failed to parse GPT response: {e}\nRaw: {raw[:300]}")
        # Return safe fallback — script unchanged, single applause at end
        return ComedyAnalysis(
            annotated_script=script,
            cues=[AudienceCue(
                offset_seconds=_estimate_duration(script),
                reaction_type="applause",
                duration_seconds=3.0,
            )],
        )

    annotated = data.get("annotated_script", script)
    raw_cues = data.get("cues", [])

    # We'll resolve "after_line" → offset_seconds during assembly using ElevenLabs timestamps
    # For now store them as-is; the assembler will match lines to timestamps
    cues = []
    for c in raw_cues:
        cues.append(AudienceCue(
            offset_seconds=-1,  # will be resolved from ElevenLabs word timestamps
            reaction_type=c.get("reaction_type", "laugh"),
            duration_seconds=float(c.get("duration_seconds", 2.0)),
        ))

    # Store the after_line hints on the cue objects for timestamp resolution
    for i, c in enumerate(cues):
        raw_cue = raw_cues[i] if i < len(raw_cues) else {}
        c.after_line = raw_cue.get("after_line", "")
        c.delay_seconds = float(raw_cue.get("delay_seconds", 0.2))

    logger.info(f"[comedy] Annotated script ready. {len(cues)} audience cues.")
    return ComedyAnalysis(annotated_script=annotated, cues=cues)


def resolve_cue_offsets(cues: List[AudienceCue], word_timestamps: list) -> List[AudienceCue]:
    """
    Match each cue's after_line to the ElevenLabs word timestamps to get
    the actual offset_seconds when the reaction should fire.

    word_timestamps: list of dicts with keys: word, start, end (seconds)
    """
    if not word_timestamps:
        return cues

    # Build a flat string of words with their end times for fuzzy matching
    words = [(w.get("word", "").lower().strip(".,!?\"'"), w.get("end", 0)) for w in word_timestamps]
    total_duration = words[-1][1] if words else 0

    for cue in cues:
        after_line = getattr(cue, "after_line", "").lower()
        delay = getattr(cue, "delay_seconds", 0.2)

        if not after_line:
            # Default: applause at end, laugh at 60% through
            if cue.reaction_type == "applause":
                cue.offset_seconds = total_duration + delay
            else:
                cue.offset_seconds = total_duration * 0.6 + delay
            continue

        # Find the last word of after_line in the timestamp list
        trigger_words = after_line.strip(".,!?\"' ").split()
        if not trigger_words:
            cue.offset_seconds = total_duration + delay
            continue

        last_trigger = trigger_words[-1].strip(".,!?\"'")
        best_end = None

        # Scan backwards through timestamps to find the last occurrence
        for word_text, word_end in reversed(words):
            if word_text == last_trigger:
                best_end = word_end
                break

        if best_end is not None:
            cue.offset_seconds = best_end + delay
        else:
            # Fallback: place at end
            cue.offset_seconds = total_duration + delay

        logger.info(f"[comedy] Cue '{cue.reaction_type}' resolved to {cue.offset_seconds:.2f}s (after '{last_trigger}')")

    return cues


def _estimate_duration(script: str) -> float:
    """Rough estimate of speech duration based on word count (~2.5 words/sec)."""
    words = len(script.split())
    return words / 2.5
