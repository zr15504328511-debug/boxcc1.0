"""Theme-aware matplotlib chart helpers — render to PNG for PPT embed.

Charts are deliberately minimal:
- One palette per deck (driven by PPTTheme).
- No gridline noise, no legend box, axis labels sized to fit the slide.
- Returns a `Path` to a PNG file written to a temp dir; caller embeds
  via `slide.shapes.add_picture`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")  # No display; we only write PNG.
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.ticker import FuncFormatter

from tools.ppt_theme import PPTTheme, chart_palette


def _resolve_cn_font() -> str | None:
    """Best-effort: find a CJK-capable font installed on the system."""
    for candidate in (
        "PingFang SC",
        "Heiti SC",
        "Hiragino Sans GB",
        "STHeiti",
        "Songti SC",
        "Noto Sans CJK SC",
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
    ):
        try:
            path = fm.findfont(candidate, fallback_to_default=False)
            if path and Path(path).exists():
                return candidate
        except Exception:
            continue
    return None


_CN_FONT = _resolve_cn_font()


def _apply_minimal_style(ax, theme: PPTTheme) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    text_color = f"#{theme.text_muted}".lower()
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(text_color)
        ax.spines[spine].set_alpha(0.4)
    ax.tick_params(colors=text_color, labelsize=9)
    ax.yaxis.grid(True, color="#000000", alpha=0.04, linewidth=0.8)
    ax.set_axisbelow(True)


def _font_kwargs() -> dict:
    if _CN_FONT:
        return {"fontname": _CN_FONT}
    return {}


def make_bar_chart(
    *,
    theme: PPTTheme,
    categories: Sequence[str],
    series: dict[str, Sequence[float]],
    title: str = "",
    y_format: str = "{:,.0f}",
    width_in: float = 8.0,
    height_in: float = 4.0,
) -> Path:
    """Vertical bar chart. If `series` has one key, draws a single-series
    chart with the accent color. If multiple, draws grouped bars in
    theme palette order.
    """
    palette = chart_palette(theme)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=160)
    fig.patch.set_facecolor(f"#{theme.bg}".lower())
    ax.set_facecolor(f"#{theme.bg}".lower())

    n_series = len(series)
    n_cats = len(categories)
    bar_total = 0.72  # total width allotted across grouped bars
    bar_w = bar_total / max(1, n_series)
    xs = list(range(n_cats))

    for i, (label, values) in enumerate(series.items()):
        offsets = [x + (i - (n_series - 1) / 2) * bar_w for x in xs]
        color = palette[i % len(palette)]
        ax.bar(offsets, values, width=bar_w, color=color, label=label, edgecolor="none")

    ax.set_xticks(xs)
    ax.set_xticklabels(categories, **_font_kwargs())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: y_format.format(v)))
    if title:
        ax.set_title(title, fontsize=12, color=f"#{theme.text}".lower(), pad=12, loc="left", **_font_kwargs())
    if n_series > 1:
        leg = ax.legend(frameon=False, fontsize=9, loc="upper left", prop=({"family": _CN_FONT} if _CN_FONT else None))
    _apply_minimal_style(ax, theme)

    out = Path(tempfile.mkstemp(prefix="boxcc_chart_", suffix=".png")[1])
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def make_line_chart(
    *,
    theme: PPTTheme,
    categories: Sequence[str],
    series: dict[str, Sequence[float]],
    title: str = "",
    y_format: str = "{:,.0f}",
    width_in: float = 8.0,
    height_in: float = 4.0,
) -> Path:
    """Multi-line chart, one line per series."""
    palette = chart_palette(theme)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=160)
    fig.patch.set_facecolor(f"#{theme.bg}".lower())
    ax.set_facecolor(f"#{theme.bg}".lower())

    xs = list(range(len(categories)))
    for i, (label, values) in enumerate(series.items()):
        color = palette[i % len(palette)]
        ax.plot(xs, values, marker="o", color=color, linewidth=2.2, markersize=6, label=label)

    ax.set_xticks(xs)
    ax.set_xticklabels(categories, **_font_kwargs())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: y_format.format(v)))
    if title:
        ax.set_title(title, fontsize=12, color=f"#{theme.text}".lower(), pad=12, loc="left", **_font_kwargs())
    if len(series) > 1:
        ax.legend(frameon=False, fontsize=9, loc="upper left", prop=({"family": _CN_FONT} if _CN_FONT else None))
    _apply_minimal_style(ax, theme)

    out = Path(tempfile.mkstemp(prefix="boxcc_chart_", suffix=".png")[1])
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def make_pie_chart(
    *,
    theme: PPTTheme,
    labels: Sequence[str],
    values: Sequence[float],
    title: str = "",
    width_in: float = 6.0,
    height_in: float = 4.5,
) -> Path:
    """Donut-style pie (a hole in the middle, modern look)."""
    palette = chart_palette(theme)
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=160)
    fig.patch.set_facecolor(f"#{theme.bg}".lower())
    ax.set_facecolor(f"#{theme.bg}".lower())

    colors = [palette[i % len(palette)] for i in range(len(labels))]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colors,
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": f"#{theme.bg}".lower(), "linewidth": 2},
        textprops={"fontsize": 10, "color": f"#{theme.text}".lower(), **_font_kwargs()},
        autopct="%1.0f%%",
        pctdistance=0.78,
    )
    for at in autotexts:
        at.set_color("#ffffff")
        at.set_fontsize(9)
        if _CN_FONT:
            at.set_fontname(_CN_FONT)
    if title:
        ax.set_title(title, fontsize=12, color=f"#{theme.text}".lower(), pad=12, **_font_kwargs())
    ax.axis("equal")

    out = Path(tempfile.mkstemp(prefix="boxcc_chart_", suffix=".png")[1])
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out
