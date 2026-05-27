"""Brand theme + design tokens for management-grade PPT decks.

Design philosophy:
- Editorial minimalism (think McKinsey / The Business of Fashion executive
  decks): generous whitespace, one strong accent color, sans-serif type,
  visible hierarchy via size + color rather than via boxes and lines.
- Cover and section dividers carry the brand "voice" — a solid color
  block, oversized title, small caps subtitle.
- Content slides stay calm: title bar at top, body below, optional
  callout box on the right. Bullets are rare; prefer numbered cards or
  short paragraph blocks.
- Data slides put one chart center-stage with a single takeaway
  sentence at the top — never multiple charts fighting for attention.
- Every slide carries a footer (page number + brand) so a printed deck
  reads as a coherent document.

Themes here are intentionally limited to two flavors; extending requires
picking a new palette but reusing the same token names so the builder
doesn't need to special-case anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pptx.dml.color import RGBColor
from pptx.util import Pt


@dataclass
class PPTTheme:
    """All design tokens for a deck. Pass to ManagementPPTBuilder."""

    name: str

    # Palette
    primary: RGBColor          # Used for cover background, divider, accents
    accent: RGBColor           # Highlight color for callouts, chart bars
    text: RGBColor             # Body text
    text_muted: RGBColor       # Subtitles, footers, captions
    bg: RGBColor               # Main slide background (typically near-white)
    subtle: RGBColor           # Cards, table stripes — barely-there fill

    # Type scale (pt)
    title_cover: int = 48
    title_section: int = 40
    title_slide: int = 28
    body: int = 18
    callout: int = 16
    footer: int = 9
    chart_title: int = 14

    # Font family (latin + east-asian). PowerPoint will substitute if absent.
    font_latin: str = "Helvetica Neue"
    font_east_asian: str = "PingFang SC"

    # Layout (inches)
    margin_left: float = 0.6
    margin_right: float = 0.6
    margin_top: float = 0.55
    margin_bottom: float = 0.45
    title_height: float = 0.9


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#"))


# Editorial: serious, calm, suitable for management briefings.
THEME_EDITORIAL = PPTTheme(
    name="editorial",
    primary=_rgb("1f2937"),    # deep slate
    accent=_rgb("a37e5c"),     # warm wood / camel
    text=_rgb("1a1a1a"),
    text_muted=_rgb("6b6b6b"),
    bg=_rgb("fafaf7"),         # warm off-white
    subtle=_rgb("ece9e0"),     # subtle card fill
)

# Cool: charcoal + steel blue, sharper feel for data-heavy decks.
THEME_COOL = PPTTheme(
    name="cool",
    primary=_rgb("0f172a"),
    accent=_rgb("2563eb"),
    text=_rgb("111827"),
    text_muted=_rgb("64748b"),
    bg=_rgb("f8fafc"),
    subtle=_rgb("e2e8f0"),
)

# Warm: fashion-editorial leaning, suitable for brand-side decks.
THEME_WARM = PPTTheme(
    name="warm",
    primary=_rgb("2c2418"),
    accent=_rgb("c97f4a"),
    text=_rgb("1c1714"),
    text_muted=_rgb("7d6a5a"),
    bg=_rgb("fbf7f0"),
    subtle=_rgb("ebe1d2"),
)

THEMES: dict[str, PPTTheme] = {
    "editorial": THEME_EDITORIAL,
    "cool": THEME_COOL,
    "warm": THEME_WARM,
}


def get_theme(name: str | None) -> PPTTheme:
    """Resolve a theme by name; fall back to editorial."""
    if not name:
        return THEME_EDITORIAL
    return THEMES.get(name.lower(), THEME_EDITORIAL)


# Matplotlib chart palette derived from the theme (kept here so charts.py
# can import without pulling pptx). The order matches theme list above.
def chart_palette(theme: PPTTheme) -> list[str]:
    """Return hex color list for chart series; first entry is the accent."""
    accent_hex = f"#{theme.accent}".lower()
    # Build a tonal palette that reads well alongside the accent.
    if theme.name == "cool":
        return [accent_hex, "#94a3b8", "#475569", "#cbd5e1", "#1e293b"]
    if theme.name == "warm":
        return [accent_hex, "#8c6a4a", "#d4a373", "#5a4634", "#c0a585"]
    return [accent_hex, "#8b8475", "#5a5346", "#c5beb0", "#3d362b"]
