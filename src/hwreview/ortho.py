"""Orthographic engineering sheets for each modelled hardware item (third-angle layout).

Plan (looking down -z), front elevation (looking +y), right elevation (looking -x)
and an isometric view, drawn from the same primitives that generate the CFD
geometry, so the drawing is exactly what was simulated. Overall dimensions are
annotated in millimetres; specimen zones, openings and membranes are coloured
and labelled; the provenance of each annotated dimension (sourced vs assumed) is
listed under the sheet.

    python -m hwreview.ortho <slug> [<slug> ...]
"""
from __future__ import annotations

import sys

import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from . import geometry, style
from .geometry import FACES
from .style import INK, INK2, MUTED, plt

ZONE_C, OBS_C, IN_C, OUT_C, MEM_C = style.GREEN, "#B9BEC6", style.BLUE, style.VERMILION, style.ORANGE
VIEWS = {"plan": (0, 1, "x (mm)", "y (mm)"), "front": (0, 2, "x (mm)", "z (mm)"), "side": (1, 2, "y (mm)", "z (mm)")}


def _draw_prim(ax, p, i, j, **kw):
    b = p.bounds()
    if p.shape == "cylinder" and {i, j} == {0, 1} and p.axis == "z":
        ax.add_patch(Circle((p.center[i], p.center[j]), p.D / 2, **kw))
    else:
        ax.add_patch(Rectangle((b[0][i], b[0][j]), b[1][i] - b[0][i], b[1][j] - b[0][j], **kw))


def _dim(ax, a, b, at, horizontal=True, label=None, off=0.0):
    if horizontal:
        ax.annotate("", (a, at + off), (b, at + off), arrowprops=dict(arrowstyle="<->", lw=0.6, color=INK2))
        ax.text((a + b) / 2, at + off, label or f"{b - a:.1f}", ha="center", va="bottom", fontsize=6.5, color=INK2,
                bbox=dict(fc="white", ec="none", pad=0.4))
    else:
        ax.annotate("", (at + off, a), (at + off, b), arrowprops=dict(arrowstyle="<->", lw=0.6, color=INK2))
        ax.text(at + off, (a + b) / 2, label or f"{b - a:.1f}", ha="left", va="center", fontsize=6.5, color=INK2,
                rotation=90, bbox=dict(fc="white", ec="none", pad=0.4))


def _openings_in_view(m, i, j, view_axis):
    """Openings lying on faces perpendicular to the view direction are drawn as filled rectangles;
    those on faces parallel to it are drawn as thick edge segments."""
    out = []
    for o in m.openings + m.membranes:
        ax_, sgn = FACES[o["face"]]
        lo, hi = m.domain.bounds()
        u, v = [a for a in range(3) if a != ax_]
        c = np.zeros(3)
        c[ax_] = hi[ax_] if sgn > 0 else lo[ax_]
        c[u], c[v] = o["center"]
        half = np.zeros(3)
        half[u], half[v] = o["size"][0] / 2, o["size"][1] / 2
        color = MEM_C if o in m.membranes else (IN_C if o.get("role") == "inlet" else OUT_C)
        out.append((o, c - half, c + half, color, ax_ == view_axis))
    return out


def sheet(slug: str):
    m = geometry.load(slug)
    style.apply()
    fig = plt.figure(figsize=(7.4, 6.6))
    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.28)
    axes = {"plan": fig.add_subplot(gs[1, 0]), "front": fig.add_subplot(gs[0, 0]),
            "side": fig.add_subplot(gs[0, 1])}
    lo, hi = m.domain.bounds()
    view_axis = {"plan": 2, "front": 1, "side": 0}
    for name, (i, j, xl, yl) in VIEWS.items():
        ax = axes[name]
        _draw_prim(ax, m.domain, i, j, fill=False, ec=INK, lw=1.4)
        for p in m.obstacles:
            _draw_prim(ax, p, i, j, fc=OBS_C, ec=MUTED, lw=0.6, alpha=0.9)
        for p in m.zones:
            _draw_prim(ax, p, i, j, fc=ZONE_C, ec=ZONE_C, lw=0.6, alpha=0.35)
        for o, a, b, col, facing in _openings_in_view(m, i, j, view_axis[name]):
            if facing:
                ax.add_patch(Rectangle((a[i], a[j]), b[i] - a[i], b[j] - a[j], fc=col, ec=col, alpha=0.5, lw=0.8))
            else:
                ax.plot([a[i], b[i]], [a[j], b[j]], color=col, lw=3.2, solid_capstyle="butt")
            ax.text((a[i] + b[i]) / 2, (a[j] + b[j]) / 2, o["name"], fontsize=5.8, color=INK, ha="center",
                    va="center")
        span = max(hi[i] - lo[i], hi[j] - lo[j])
        pad = 0.12 * span
        _dim(ax, lo[i], hi[i], lo[j], True, off=-0.07 * span)
        _dim(ax, lo[j], hi[j], hi[i], False, off=0.04 * span)
        ax.set_xlim(lo[i] - pad, hi[i] + pad)
        ax.set_ylim(lo[j] - pad, hi[j] + pad)
        ax.set_aspect("equal")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.set_title({"plan": "Plan (from +z)", "front": "Front elevation (from -y)",
                      "side": "Side elevation (from +x)"}[name], fontsize=8)
        ax.grid(False)
    # isometric
    ax3 = fig.add_subplot(gs[1, 1], projection="3d")
    dmesh = m.domain.mesh()
    sharp = dmesh.face_adjacency_edges[dmesh.face_adjacency_angles > np.radians(20)]
    for e in sharp:
        seg = dmesh.vertices[e]
        ax3.plot(seg[:, 0], seg[:, 1], seg[:, 2], color=INK, lw=0.8)
    for p, fc, a in [(p, OBS_C, 0.9) for p in m.obstacles] + [(p, ZONE_C, 0.35) for p in m.zones]:
        ax3.add_collection3d(Poly3DCollection(p.mesh().triangles, facecolors=fc, edgecolors="none", alpha=a))
    for o, a, b, col, _ in _openings_in_view(m, 0, 1, -1):
        corners = np.array([a, [b[0], a[1], a[2]] if a[0] != b[0] else a, b, b])
        ax3.scatter(*(((a + b) / 2)[None, :].T), color=col, s=14)
    ax3.set_xlim(lo[0], hi[0])
    ax3.set_ylim(lo[1], hi[1])
    ax3.set_zlim(lo[2], hi[2])
    ax3.set_box_aspect(hi - lo)
    ax3.view_init(elev=25, azim=-55)
    ax3.set_xlabel("x", fontsize=6)
    ax3.set_ylabel("y", fontsize=6)
    ax3.set_zlabel("z", fontsize=6)
    ax3.tick_params(labelsize=5)
    ax3.set_title("Isometric", fontsize=8)
    # legend + provenance footer
    handles = [Rectangle((0, 0), 1, 1, fc=OBS_C, ec=MUTED, label="solid (obstacle)"),
               Rectangle((0, 0), 1, 1, fc=ZONE_C, alpha=0.35, label="specimen zone (sources)"),
               Rectangle((0, 0), 1, 1, fc=IN_C, alpha=0.5, label="inlet"),
               Rectangle((0, 0), 1, 1, fc=OUT_C, alpha=0.5, label="outlet"),
               Rectangle((0, 0), 1, 1, fc=MEM_C, alpha=0.5, label="gas-permeable membrane")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=6.5, bbox_to_anchor=(0.5, 0.0))
    srcs = sorted({u["ref"] for u in m.provenance})
    n_assump = len(m.spec.get("assumptions") or [])
    fig.text(0.01, -0.03, f"Sourced parameters used: {len(srcs)} (hardware/{m.spec['hardware']}.yaml); "
             f"modelling assumptions: {n_assump} (models/{slug}.yaml). Dimensions in mm.",
             fontsize=6, color=INK2)
    fig.suptitle(f"{m.hw.get('name', slug)} - CFD geometry", x=0.01, ha="left", fontsize=10, fontweight="bold")
    style.save(fig, f"ortho_{slug}")


if __name__ == "__main__":
    for s in sys.argv[1:]:
        sheet(s)
