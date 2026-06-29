"""
Ad Compositor — Unified Home Remodeling
Post-processes AI-generated visuals into professional ad-quality graphics.

Layout philosophy:
  - AI generates the VISUAL SCENE ONLY (no text, no logo)
  - This script handles ALL text, CTA, logo, and layout overlays
  - Zones are proportional so they work at any resolution/aspect ratio

Zone map (top → bottom):
  ┌─────────────────────────────────┐
  │  HEADLINE ZONE  (top 18%)       │  Bold 2–5 word hook
  │  [semi-transparent scrim]       │
  ├─────────────────────────────────┤
  │                                 │
  │  VISUAL ZONE    (middle ~64%)   │  AI image shows through clean
  │                                 │
  ├─────────────────────────────────┤
  │  BOTTOM BAR     (bottom 18%)    │  Logo left | CTA pill right
  │  [solid brand bar]              │
  └─────────────────────────────────┘

Usage:
    from compositor import composite_ad
    out_path = composite_ad(
        image_path="/path/to/ai_scene.png",
        headline="New Door. New Value.",
        cta_text="Get a Free Quote",
        logo_path="/path/to/unified_logo.png",
        output_path="/path/to/output.png",
        content_type="before_after",   # tip_card | before_after | testimonial | promotional | carousel
        subtext=None,                  # optional 1 line below headline (≤6 words)
    )
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import textwrap

# ── Font paths (server) ────────────────────────────────────────────────────────
FONT_BOLD    = "/usr/share/fonts/truetype/open-sans/OpenSans-ExtraBold.ttf"
FONT_SEMIBOLD = "/usr/share/fonts/truetype/open-sans/OpenSans-SemiBold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf"
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ── Brand colours ──────────────────────────────────────────────────────────────
RED    = (196, 30, 58, 255)       # #C41E3A
DARK   = (26, 26, 26, 255)        # #1A1A1A
WHITE  = (255, 255, 255, 255)
WHITE_90 = (255, 255, 255, 230)
SCRIM_DARK = (26, 26, 26, 180)    # semi-transparent dark for headline zone
SCRIM_LIGHT = (26, 26, 26, 140)   # lighter scrim for bottom bar gradient


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype(FONT_FALLBACK, size)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int, fill: tuple):
    """Draw a filled rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def composite_ad(
    image_path: str,
    headline: str,
    cta_text: str,
    logo_path: str,
    output_path: str,
    content_type: str = "tip_card",
    subtext: str = None,
) -> str:
    """
    Composite text, CTA, and logo onto an AI-generated scene image.

    Returns the output_path string.
    """
    img = Image.open(image_path).convert("RGBA")
    W, H = img.size

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── Zone heights ────────────────────────────────────────────────────────────
    headline_h = int(H * 0.18)
    bottom_h   = int(H * 0.18)
    safe_pad   = int(W * 0.05)   # 5% horizontal padding

    # ── HEADLINE ZONE — top scrim + text ───────────────────────────────────────
    # Gradient scrim: opaque at top, fades to transparent
    for y in range(headline_h):
        alpha = int(SCRIM_DARK[3] * (1 - y / headline_h))
        draw.rectangle([(0, y), (W, y + 1)], fill=(26, 26, 26, alpha))

    # Headline font — scale to fit in ~80% of width, max 3 lines
    headline_font_size = max(36, int(H * 0.072))
    headline_font = _load_font(FONT_BOLD, headline_font_size)
    headline_lines = _wrap_text(headline.upper(), headline_font, int(W * 0.88), draw)

    # If headline is too tall, reduce font size
    while len(headline_lines) > 2 and headline_font_size > 28:
        headline_font_size -= 4
        headline_font = _load_font(FONT_BOLD, headline_font_size)
        headline_lines = _wrap_text(headline.upper(), headline_font, int(W * 0.88), draw)

    line_h = draw.textbbox((0, 0), "Ag", font=headline_font)[3]
    total_text_h = len(headline_lines) * (line_h + 4)
    text_y = (headline_h - total_text_h) // 2

    for line in headline_lines:
        bbox = draw.textbbox((0, 0), line, font=headline_font)
        text_w = bbox[2] - bbox[0]
        x = (W - text_w) // 2
        # Drop shadow
        draw.text((x + 2, text_y + 2), line, font=headline_font, fill=(0, 0, 0, 160))
        draw.text((x, text_y), line, font=headline_font, fill=WHITE)
        text_y += line_h + 4

    # Optional subtext below headline (e.g. "Westchester's #1 Choice")
    if subtext:
        sub_font_size = max(20, int(H * 0.032))
        sub_font = _load_font(FONT_SEMIBOLD, sub_font_size)
        sub_bbox = draw.textbbox((0, 0), subtext, font=sub_font)
        sub_w = sub_bbox[2] - sub_bbox[0]
        sub_x = (W - sub_w) // 2
        sub_y = text_y + 4
        draw.text((sub_x + 1, sub_y + 1), subtext, font=sub_font, fill=(0, 0, 0, 140))
        draw.text((sub_x, sub_y), subtext, font=sub_font, fill=WHITE_90)

    # ── BOTTOM BAR — solid dark bar ─────────────────────────────────────────────
    bar_y = H - bottom_h
    draw.rectangle([(0, bar_y), (W, H)], fill=DARK)

    # Thin red accent line at top of bar
    accent_h = max(3, int(H * 0.004))
    draw.rectangle([(0, bar_y), (W, bar_y + accent_h)], fill=RED)

    # Logo — left side of bar
    logo_zone_w = int(W * 0.45)
    try:
        logo_raw = Image.open(logo_path).convert("RGBA")
        lw, lh = logo_raw.size
        # Scale to fit in logo zone height (70% of bar height)
        max_logo_h = int(bottom_h * 0.70)
        max_logo_w = logo_zone_w - safe_pad * 2
        scale = min(max_logo_w / lw, max_logo_h / lh)
        new_lw = int(lw * scale)
        new_lh = int(lh * scale)
        logo_resized = logo_raw.resize((new_lw, new_lh), Image.LANCZOS)
        logo_x = safe_pad
        logo_y = bar_y + (bottom_h - new_lh) // 2
        overlay.paste(logo_resized, (logo_x, logo_y), logo_resized)
    except Exception as e:
        pass  # Logo failure is non-fatal

    # CTA pill — right side of bar (only rendered if cta_text is provided)
    if cta_text and cta_text.strip():
        cta_font_size = max(22, int(H * 0.038))
        cta_font = _load_font(FONT_BOLD, cta_font_size)
        cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
        cta_w = cta_bbox[2] - cta_bbox[0]
        cta_h_text = cta_bbox[3] - cta_bbox[1]

        pill_pad_x = int(W * 0.04)
        pill_pad_y = int(H * 0.018)
        pill_w = cta_w + pill_pad_x * 2
        pill_h = cta_h_text + pill_pad_y * 2
        pill_radius = pill_h // 2

        pill_x1 = W - safe_pad - pill_w
        pill_y1 = bar_y + (bottom_h - pill_h) // 2
        pill_x2 = W - safe_pad
        pill_y2 = pill_y1 + pill_h

        _draw_rounded_rect(draw, (pill_x1, pill_y1, pill_x2, pill_y2), pill_radius, RED)

        # True center: account for bbox[0]/bbox[1] offsets (font metrics can shift origin)
        cta_text_x = pill_x1 + (pill_w - cta_w) // 2 - cta_bbox[0]
        cta_text_y = pill_y1 + (pill_h - cta_h_text) // 2 - cta_bbox[1]
        draw.text((cta_text_x, cta_text_y), cta_text, font=cta_font, fill=WHITE)

    # ── Composite and save ──────────────────────────────────────────────────────
    result = Image.alpha_composite(img, overlay)
    result = result.convert("RGB")
    result.save(output_path, format="PNG", quality=95)
    return output_path


# ── CTA defaults per content type ─────────────────────────────────────────────
DEFAULT_CTA = {
    "tip_card":     "Get a Free Quote",
    "before_after": "See Your Transformation",
    "testimonial":  "Join Our Happy Customers",
    "promotional":  "Call Now — Limited Offer",
    "carousel":     "Learn More",
}

DEFAULT_HEADLINE = {
    "tip_card":     "Did You Know?",
    "before_after": "See the Difference",
    "testimonial":  "Real Results. Real Homeowners.",
    "promotional":  "Limited Time Offer",
    "carousel":     "Home Tips from Unity",
}
