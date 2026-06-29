"""
Script writer — generates video scripts using GPT-4.1-mini.
Brand/mascot references are loaded from clients.json via client_config.
Formats: myth_or_fact | quick_tip | did_you_know | comedy | announcement | story
Lengths: 8s | 15s | 20s
"""
import os
from openai import OpenAI
from .client_config import get_client

LENGTH_WORD_GUIDE = {
    "8s":  "25–35 words",
    "15s": "50–65 words",
    "20s": "70–90 words",
}

# Format templates use {mascot}, {brand}, {topic}, {length_guide} placeholders
FORMAT_TEMPLATES = {
    "myth_or_fact": """Write a "Myth or Fact?" {industry} video script for {mascot}, a friendly mascot for {brand}.
Format:
"Myth or fact? [STATE THE MYTH OR FACT AS A QUESTION].
That's a [myth/fact]!
[1–2 sentence explanation].
Follow for more home tips from {brand}!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",

    "quick_tip": """Write a "Quick Tip" {industry} video script for {mascot}, a friendly mascot for {brand}.
Format:
"Quick tip! [ACTIONABLE TIP ABOUT THE TOPIC].
[1–2 sentences expanding on why this matters or how to do it].
Follow {brand} for more home tips!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",

    "did_you_know": """Write a "Did You Know?" {industry} video script for {mascot}, a friendly mascot for {brand}.
Format:
"Did you know? [SURPRISING FACT ABOUT THE TOPIC].
[1–2 sentences with more context or a follow-up tip].
Follow {brand} for more home improvement facts!"

Topic: {topic}
Target length: {length_guide}
Keep it conversational, energetic, and educational. No hashtags. No emojis.""",

    "comedy": """Write a short comedy video script for {mascot}, a friendly mascot for {brand}.
The script should be funny and relatable — like a quick joke, a playful observation, or a lighthearted skit about {industry}.
{mascot} can be self-aware, a little goofy, or react to a common customer frustration with humor.
End with a light call to action like "Follow {brand} for more!" or a punchline that lands naturally.

Topic / premise: {topic}
Target length: {length_guide}
Keep it punchy and fun. Sentence case only. No hashtags. No emojis.""",

    "announcement": """Write a short announcement video script for {mascot}, a friendly mascot for {brand}.
The script should be upbeat and exciting — like {mascot} is sharing big news, a special offer, a seasonal promotion, or a company update.
Open with energy (e.g. "Big news!", "Exciting update!", "Heads up!") and close with a clear call to action.

Announcement topic: {topic}
Target length: {length_guide}
Keep it enthusiastic and clear. Sentence case only. No hashtags. No emojis.""",

    "story": """Write a short story-style video script for {mascot}, a friendly mascot for {brand}.
The script should feel like a mini narrative — a before-and-after, a customer's journey, or a relatable situation that ends with a satisfying resolution.
{mascot} narrates or is part of the story. End with a warm takeaway or call to action.

Story topic / scenario: {topic}
Target length: {length_guide}
Keep it warm, engaging, and relatable. Sentence case only. No hashtags. No emojis.""",
}


def generate_script(topic: str, format: str, length: str, client_id: str = "unified") -> str:
    """Generate a video script using GPT-4.1-mini with client-specific brand voice."""
    client_cfg = get_client(client_id)
    brand = client_cfg.get("brand_name", "the company")
    mascot = client_cfg.get("mascot_name", "the mascot")
    industry = client_cfg.get("industry", "home improvement")
    persona = client_cfg.get("script_persona", f"You are a professional video scriptwriter for {brand}.")

    openai_client = OpenAI()
    length_guide = LENGTH_WORD_GUIDE.get(length, "35–50 words")
    template = FORMAT_TEMPLATES.get(format, FORMAT_TEMPLATES["myth_or_fact"])
    prompt = template.format(
        topic=topic,
        length_guide=length_guide,
        brand=brand,
        mascot=mascot,
        industry=industry,
    )

    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    f"{persona} "
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
