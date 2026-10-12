"""Shared figure style (Okabe-Ito; validated with the dataviz palette checker).

Categorical hardware-class palette checked 2026-10-12: lightness, chroma, CVD
(worst adjacent deutan dE 11.0) and normal-vision floors PASS; orange and pink are
below 3:1 contrast on white, so every figure direct-labels or tabulates them.
"""
from __future__ import annotations

import os

os.environ.setdefault("SOURCE_DATE_EPOCH", "1735689600")  # byte-reproducible PDFs

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#1A1D21"
INK2 = "#52514E"
MUTED = "#8A8F98"
GRID = "#E3E5E8"
SURFACE = "#FFFFFF"

GREEN, VERMILION, BLUE, ORANGE, PINK, SKY, YELLOW = (
    "#009E73", "#D55E00", "#0072B2", "#E69F00", "#CC79A7", "#56B4E9", "#F0E442")

CLASS_COLOR = {"plant": GREEN, "rodent": VERMILION, "other_animal": BLUE, "cell_microbe": ORANGE, "mixed": PINK}
CLASS_LABEL = {"plant": "Plant", "rodent": "Rodent", "other_animal": "Other animal",
               "cell_microbe": "Cell / microbe", "mixed": "Mixed"}
# ordinal evidence levels: one hue, light -> dark
LEVEL_COLOR = {0.0: "#E3E5E8", 0.5: "#8DB8DA", 1.0: "#0B4F84"}
GRAVITY_COLOR = {"0g": BLUE, "1g": VERMILION}


def apply():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.linewidth": 0.6,
        "xtick.color": INK2, "ytick.color": INK2, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight", "pdf.fonttype": 42,
        "text.color": INK, "axes.titleweight": "bold", "axes.titlelocation": "left",
    })


def save(fig, path_stem):
    from .paths import FIGURES
    FIGURES.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIGURES / f"{path_stem}.{ext}", metadata={"CreationDate": None} if ext == "pdf" else None)
    plt.close(fig)
