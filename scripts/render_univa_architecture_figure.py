#!/usr/bin/env python3
"""Render the UniVA paper architecture figure as SVG, PDF, and PNG."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "paper_assets"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

COLORS = {
    "ink": "#172033",
    "muted": "#526174",
    "line": "#8290A3",
    "paper": "#FFFFFF",
    "codex": "#D97706",
    "codex_light": "#FFF7E8",
    "skill": "#18766F",
    "skill_light": "#E9F7F4",
    "backend": "#2F5F9F",
    "backend_light": "#EDF4FC",
    "frontend": "#9A4D63",
    "frontend_light": "#FBEFF3",
    "media": "#53657A",
    "media_light": "#F0F3F7",
    "green": "#43835A",
    "green_light": "#EDF7EF",
}


def font(size: float, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REGULAR
    return font_manager.FontProperties(fname=path, size=size)


def rounded_box(ax, x, y, w, h, face, edge, radius=0.8, lw=1.4, z=2):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.28,rounding_size={radius}",
        linewidth=lw,
        edgecolor=edge,
        facecolor=face,
        zorder=z,
    )
    ax.add_patch(patch)
    return patch


def label(ax, x, y, text, size=9, color=None, bold=False, ha="center", va="center", z=5):
    ax.text(
        x,
        y,
        text,
        color=color or COLORS["ink"],
        fontproperties=font(size, bold),
        ha=ha,
        va=va,
        linespacing=1.25,
        zorder=z,
    )


def arrow(
    ax,
    start,
    end,
    color=None,
    lw=1.6,
    style="-|>",
    dashed=False,
    curve=0.0,
    z=3,
):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle=style,
        mutation_scale=12,
        linewidth=lw,
        color=color or COLORS["line"],
        linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={curve}",
        shrinkA=1,
        shrinkB=1,
        zorder=z,
    )
    ax.add_patch(patch)
    return patch


def pill(ax, x, y, w, text, face, edge, text_color=None, size=7.8):
    rounded_box(ax, x, y, w, 3.5, face, edge, radius=1.6, lw=0.9, z=4)
    label(ax, x + w / 2, y + 1.75, text, size=size, color=text_color or COLORS["ink"], z=6)


def draw():
    plt.rcParams.update(
        {
            "figure.facecolor": COLORS["paper"],
            "savefig.facecolor": COLORS["paper"],
            "svg.fonttype": "path",
            "pdf.fonttype": 42,
            "axes.unicode_minus": False,
        }
    )

    fig, ax = plt.subplots(figsize=(16, 9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 62)
    ax.axis("off")

    label(
        ax,
        50,
        59.2,
        "UniVA Architecture: Codex Collaboration, Skills, and Editable Video Production Loop",
        size=16,
        bold=True,
    )
    label(
        ax,
        50,
        56.7,
        "UniVA Architecture: Agent Collaboration, Shared Skills, and Human-Editable Production",
        size=7.8,
        color=COLORS["muted"],
    )

    # Creator entry point
    rounded_box(ax, 2.0, 48.0, 13.5, 6.0, "#F7F8FA", COLORS["line"], lw=1.1)
    label(ax, 8.75, 51.8, "Creator", size=10.5, bold=True)
    label(ax, 8.75, 49.7, "Creator", size=7.2, color=COLORS["muted"])

    # Shared skill layer
    rounded_box(ax, 20.0, 47.2, 77.0, 7.8, COLORS["skill_light"], COLORS["skill"], lw=1.7)
    label(ax, 23.0, 52.5, "Shared Skill Knowledge Layer", size=11.5, color=COLORS["skill"], bold=True, ha="left")
    label(ax, 23.0, 49.8, "Shared domain knowledge and governance", size=7.3, color=COLORS["muted"], ha="left")
    pill(ax, 49.0, 49.2, 8.0, "Core", "#FFFFFF", COLORS["skill"], COLORS["skill"])
    pill(ax, 58.0, 49.2, 10.0, "Creative", "#FFFFFF", COLORS["skill"], COLORS["skill"])
    pill(ax, 69.0, 49.2, 8.0, "Meta", "#FFFFFF", COLORS["skill"], COLORS["skill"])
    pill(ax, 78.0, 49.2, 9.0, "Pipeline", "#FFFFFF", COLORS["skill"], COLORS["skill"])
    pill(ax, 88.0, 49.2, 7.0, "User", "#FFFFFF", COLORS["skill"], COLORS["skill"])

    # Four emphasized system regions
    rounded_box(ax, 2.0, 18.0, 21.0, 25.8, COLORS["codex_light"], COLORS["codex"], lw=2.0)
    label(ax, 4.2, 40.9, "1  External Agent Collaboration", size=11.2, color=COLORS["codex"], bold=True, ha="left")
    label(ax, 4.2, 38.5, "External agent collaboration", size=7.1, color=COLORS["muted"], ha="left")
    rounded_box(ax, 4.2, 30.2, 16.6, 6.2, "#FFFFFF", COLORS["codex"], lw=1.2)
    label(ax, 12.5, 34.2, "Codex", size=13, color=COLORS["codex"], bold=True)
    label(ax, 12.5, 31.8, "Research · Plan · Execute · Verify", size=7.5, color=COLORS["muted"])
    rounded_box(ax, 4.2, 24.2, 16.6, 4.2, "#FFFFFF", "#C8964A", lw=1.0)
    label(ax, 12.5, 26.3, "Other Terminal Agents", size=8.3, bold=True)
    rounded_box(ax, 4.2, 19.7, 16.6, 3.0, "#FFF1D8", "#D7A14C", lw=0.9)
    label(ax, 12.5, 21.2, "Direct Runners", size=8.0, color=COLORS["codex"], bold=True)

    rounded_box(ax, 27.0, 18.0, 41.0, 25.8, COLORS["backend_light"], COLORS["backend"], lw=2.0)
    label(ax, 29.3, 40.9, "3  Autonomous Backend", size=11.2, color=COLORS["backend"], bold=True, ha="left")
    label(ax, 29.3, 38.5, "Standalone orchestration backend", size=7.1, color=COLORS["muted"], ha="left")
    rounded_box(ax, 29.4, 33.0, 36.2, 3.7, "#FFFFFF", "#7192BC", lw=1.0)
    label(ax, 47.5, 34.85, "FastAPI · Session State · SSE · Project Context", size=8.1, bold=True)
    rounded_box(ax, 29.4, 26.8, 17.1, 4.5, "#FFFFFF", COLORS["backend"], lw=1.1)
    label(ax, 37.95, 29.8, "Plan-Act", size=9.8, color=COLORS["backend"], bold=True)
    label(ax, 37.95, 28.0, "Planning and Execution Support", size=6.7, color=COLORS["muted"])
    rounded_box(ax, 48.5, 26.8, 17.1, 4.5, "#FFFFFF", COLORS["green"], lw=1.1)
    label(ax, 57.05, 29.8, "Pipeline · Checkpoint", size=8.8, color=COLORS["green"], bold=True)
    label(ax, 57.05, 28.0, "Stage Orchestration and Human Approval", size=6.7, color=COLORS["muted"])
    rounded_box(ax, 29.4, 20.2, 36.2, 4.7, "#DDEAF8", COLORS["backend"], lw=1.2)
    label(ax, 47.5, 23.25, "MCP Tool Adapters and Normalized I/O", size=9.6, color=COLORS["backend"], bold=True)
    label(ax, 47.5, 21.4, "MCP adapters · ToolResponse · validation", size=6.6, color=COLORS["muted"])

    rounded_box(ax, 72.0, 18.0, 26.0, 25.8, COLORS["frontend_light"], COLORS["frontend"], lw=2.0)
    label(ax, 74.2, 40.9, "4  AI Chat and Editor", size=11.2, color=COLORS["frontend"], bold=True, ha="left")
    label(ax, 74.2, 38.5, "Human-editable Web workspace", size=7.1, color=COLORS["muted"], ha="left")
    rounded_box(ax, 74.2, 33.1, 21.6, 3.8, "#FFFFFF", COLORS["frontend"], lw=1.1)
    label(ax, 85.0, 35.0, "AI Chat · Approval Interaction", size=8.8, color=COLORS["frontend"], bold=True)
    rounded_box(ax, 74.2, 28.2, 21.6, 3.5, "#FFFFFF", "#B77C8D", lw=1.0)
    label(ax, 85.0, 29.95, "Dynamic Media Library", size=8.0, bold=True)
    rounded_box(ax, 74.2, 23.3, 10.0, 3.4, "#FFFFFF", "#B77C8D", lw=1.0)
    label(ax, 79.2, 25.0, "Preview", size=8.0, bold=True)
    rounded_box(ax, 85.8, 23.3, 10.0, 3.4, "#FFFFFF", "#B77C8D", lw=1.0)
    label(ax, 90.8, 25.0, "Properties", size=8.0, bold=True)
    rounded_box(ax, 74.2, 19.6, 15.2, 2.4, "#F6DDE5", COLORS["frontend"], lw=0.9)
    label(ax, 81.8, 20.8, "Nonlinear Timeline", size=7.7, color=COLORS["frontend"], bold=True)
    rounded_box(ax, 91.0, 19.6, 4.8, 2.4, "#F6DDE5", COLORS["frontend"], lw=0.9)
    label(ax, 93.4, 20.8, "Export", size=7.4, color=COLORS["frontend"], bold=True)

    # Layer number 2 marker emphasizes skills as a primary contribution.
    rounded_box(ax, 40.8, 52.0, 6.0, 2.0, COLORS["skill"], COLORS["skill"], radius=1.0, lw=0.8, z=7)
    label(ax, 43.8, 53.0, "2", size=8.5, color="#FFFFFF", bold=True, z=8)

    # Bottom execution and persistence layers
    rounded_box(ax, 2.0, 5.5, 66.0, 8.2, COLORS["media_light"], COLORS["media"], lw=1.5)
    label(ax, 4.2, 11.7, "Media Execution Capabilities", size=9.3, color=COLORS["media"], bold=True, ha="left")
    pill(ax, 18.0, 7.2, 8.3, "Video Gen", "#FFFFFF", "#7C8998", size=7.2)
    pill(ax, 27.2, 7.2, 8.3, "Image Gen", "#FFFFFF", "#7C8998", size=7.2)
    pill(ax, 36.4, 7.2, 8.3, "Understand/Track", "#FFFFFF", "#7C8998", size=7.2)
    pill(ax, 45.6, 7.2, 8.3, "Video Edit", "#FFFFFF", "#7C8998", size=7.2)
    pill(ax, 54.8, 7.2, 5.2, "Audio", "#FFFFFF", "#7C8998", size=7.2)
    pill(ax, 60.9, 7.2, 5.0, "Compose", "#FFFFFF", "#7C8998", size=7.2)

    rounded_box(ax, 72.0, 5.5, 26.0, 8.2, COLORS["green_light"], COLORS["green"], lw=1.5)
    label(ax, 74.2, 11.7, "Project Data and Artifacts", size=9.3, color=COLORS["green"], bold=True, ha="left")
    pill(ax, 74.2, 7.2, 8.0, "data/", "#FFFFFF", "#75A583", COLORS["green"], size=7.4)
    pill(ax, 83.0, 7.2, 7.0, "results/", "#FFFFFF", "#75A583", COLORS["green"], size=7.4)
    pill(ax, 90.8, 7.2, 4.8, "Project", "#FFFFFF", "#75A583", COLORS["green"], size=7.4)

    # Main interactions
    arrow(ax, (15.5, 50.4), (20.0, 50.4), COLORS["line"], lw=1.4)
    arrow(ax, (8.4, 48.0), (10.5, 43.8), COLORS["codex"], lw=1.4, curve=0.08)
    arrow(ax, (15.2, 48.0), (76.0, 43.8), COLORS["frontend"], lw=1.3, curve=-0.12)
    label(ax, 50.0, 46.0, "Natural-Language Goals and Human Decisions", size=6.8, color=COLORS["muted"])

    # Skill governance arrows
    arrow(ax, (31.0, 47.2), (15.5, 43.8), COLORS["skill"], lw=1.25, dashed=True)
    arrow(ax, (57.0, 47.2), (51.0, 43.8), COLORS["skill"], lw=1.25, dashed=True)
    label(ax, 35.2, 45.2, "Load / Constrain", size=6.5, color=COLORS["skill"])

    # Codex to backend and direct execution paths
    arrow(ax, (23.0, 32.0), (27.0, 32.0), COLORS["codex"], lw=1.8)
    label(ax, 25.0, 34.0, "API", size=6.5, color=COLORS["muted"])
    arrow(ax, (12.5, 19.7), (22.0, 13.7), COLORS["codex"], lw=1.5, dashed=True, curve=0.06)
    label(ax, 16.4, 15.9, "Direct Tool Function Reuse", size=6.3, color=COLORS["codex"])

    # Backend <-> frontend and execution paths
    arrow(ax, (68.0, 34.7), (72.0, 34.7), COLORS["backend"], lw=1.7, style="<|-|>")
    label(ax, 70.0, 37.0, "HTTP/SSE", size=6.3, color=COLORS["muted"])
    arrow(ax, (47.5, 20.2), (47.5, 13.7), COLORS["backend"], lw=1.7)
    arrow(ax, (85.0, 18.0), (85.0, 13.7), COLORS["frontend"], lw=1.6, style="<|-|>")
    label(ax, 88.0, 15.9, "Assets/State", size=6.3, color=COLORS["muted"])
    arrow(ax, (68.0, 21.8), (72.0, 11.2), COLORS["green"], lw=1.25, dashed=True, curve=0.08)

    # Compact legend
    arrow(ax, (3.0, 2.6), (7.5, 2.6), COLORS["line"], lw=1.4)
    label(ax, 8.3, 2.6, "Control/Data Interaction", size=6.4, color=COLORS["muted"], ha="left")
    arrow(ax, (23.5, 2.6), (28.0, 2.6), COLORS["skill"], lw=1.3, dashed=True)
    label(ax, 28.8, 2.6, "Knowledge and Constraints", size=6.4, color=COLORS["muted"], ha="left")
    label(
        ax,
        97.5,
        2.6,
        "Core Contributions: 1 Codex Collaboration · 2 Skills · 3 Autonomous Backend · 4 AI Chat/Editor",
        size=6.5,
        color=COLORS["muted"],
        ha="right",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUTPUT_DIR / "figure_1_univa_architecture"
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.08)
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.08)
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


if __name__ == "__main__":
    draw()
