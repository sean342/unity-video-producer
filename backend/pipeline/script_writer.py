"""
Script writer — generates Unity video scripts using GPT-4.1-mini.
Formats: myth_or_fact | quick_tip | did_you_know
Lengths: 8s | 15s | 20s
"""
import os
from openai import OpenAI

client = OpenAI()  # uses OPENAI_API_KEY env var

LENGTH_WORD_GUIDE = {
    "8s":  "25–35 words",
    "15s": "50–65 words",
    "20s": "70–90 words",
}

FORMAT_TEMPLATES = {
    "myth_or_fact": """Write a "Myth or Fact?" home improvement video script for Unity, a friendly golden retriever mascot.
Format:
"Myth or fact? [STATE THE MYTH OR FACT AS A QUESTION].
That's a [myth/fact]!
[1–2 sentence explanation].
Follow for more home tips from Unified!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",

    "quick_tip": """Write a "Quick Tip" home improvement video script for Unity, a friendly golden retriever mascot.
Format:
"Quick tip! [ACTIONABLE TIP ABOUT THE TOPIC].
[1–2 sentences expanding on why this matters or how to do it].
Follow Unified for more home tips!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",

    "did_you_know": """Write a "Did You Know?" home improvement video script for Unity, a friendly golden retriever mascot.
Format:
"Did you know? [SURPRISING FACT ABOUT THE TOPIC].
[1–2 sentences with more context or a follow-up tip].
Follow Unified for more home improvement facts!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",
}


def generate_script(topic: str, format: str, length: str) -> str:
    """Generate a Unity video script using GPT-4.1-mini."""
    length_guide = LENGTH_WORD_GUIDE.get(length, "35–50 words")
    template = FORMAT_TEMPLATES.get(format, FORMAT_TEMPLATES["myth_or_fact"])
    prompt = template.format(topic=topic, length_guide=length_guide)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional video scriptwriter for Unified Home Remodeling. "
                    "Write short, punchy scripts for Unity the golden retriever mascot. "
                    "Always use sentence case (never ALL CAPS). "
                    "Output ONLY the script text — no labels, no quotes, no extra commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
