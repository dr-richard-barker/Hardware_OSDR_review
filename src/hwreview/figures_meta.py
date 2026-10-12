"""Figures for the catalogue assessment and metadata meta-analysis (F1-F5).

Every number drawn is read from results/tables/* written by earlier stages;
nothing is typed in here.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import style
from .paths import TABLES
from .style import CLASS_COLOR, CLASS_LABEL, INK, INK2, LEVEL_COLOR, MUTED, plt  # noqa: F401


SHORT = {"HW033": "Veggie", "HW034": "APH", "HW142": "Rodent Habitat", "HW232": "AEM Transporter",
         "HW068": "AEM", "HW025": "BRIC-PDFU", "HW040": "Kubik", "HW027": "GAP-FPA", "HW105": "JAXA MHU",
         "HW042": "EMCS", "HW037": "CBEF/PEU", "HW234": "Vented Fly Box", "HW036": "MVP", "HW019": "BioCell",
         "HW215": "VFEU", "HW220": "E150 EUE", "HW205": "BOTEX", "HW150": "Jellyfish Kit", "HW024": "BRIC-100",
         "HW044": "CGBA", "HW191": "RAHF", "HW121": "MOBIAS", "HW228": "FIT Fly Kit"}


def _counts():
    n = pd.read_csv(TABLES / "T2_counts.csv")
    return {(g, k): v for g, k, v in n[["group", "key", "n"]].values}


def fig1_funnel():
    c = _counts()
    meta = pd.read_csv(TABLES / "T4a_habitat_meta.csv")
    s = json.loads((TABLES / "T4_summary.json").read_text())
    tiers = s["tier_sensitivity"]["public_tier"]
    rows = [
        ("Hardware entities (all sources)", c[("total", "hardware entities")]),
        ("  in SPLASH", c[("total", "in SPLASH")]),
        ("  in OSDR hardware registry", c[("total", "in OSDR registry")]),
        ("Can carry space-biology payloads", c[("bio", "bio-payload capable")]),
        ("House live specimens in flight", len(meta)),
        ("  ... linked to >=1 OSDR study", int((meta.n_osd_studies > 0).sum())),
        ("CFD-ready from public metadata (Tier A)", tiers.get("A", 0)),
    ]
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    y = np.arange(len(rows))[::-1]
    vals = [r[1] for r in rows]
    colors = [style.BLUE if not r[0].startswith("  ") else style.SKY for r in rows]
    colors[-1] = style.VERMILION
    ax.barh(y, vals, height=0.62, color=colors, edgecolor="white", linewidth=1.5)
    for yi, (lab, v) in zip(y, rows):
        ax.text(-6, yi, lab.strip(), ha="right", va="center", color=INK, fontsize=7.5)
        ax.text(v + 4, yi, f"{v}", ha="left", va="center", color=INK, fontsize=7.5, fontweight="bold")
    ax.set_yticks([])
    ax.set_xlim(0, max(vals) * 1.12)
    ax.set_xlabel("Number of hardware entities")
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", visible=False)
    ax.set_title("Space-biology hardware in NASA catalogues", x=-0.62)
    style.save(fig, "F1_catalogue_funnel")


def fig2_items():
    it = pd.read_csv(TABLES / "T4c_item_missingness.csv")
    it = it.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    y = np.arange(len(it))
    left = np.zeros(len(it))
    for col, lev, lab in (("quantitative", 1.0, "quantitative"), ("qualitative", 0.5, "qualitative only"),
                          ("absent", 0.0, "absent")):
        ax.barh(y, it[col] * 100, left=left, color=LEVEL_COLOR[lev], height=0.7, edgecolor="white",
                linewidth=1.2, label=lab)
        left += it[col].values * 100
    ax.scatter(it.splash_quantitative * 100, y, marker="|", s=90, color=INK, linewidths=1.6,
               label="quantitative in SPLASH alone", zorder=3)
    labels = [f"{r.item}  {r.label}{' *' if r.critical else ''}" for r in it.itertuples()]
    ax.set_yticks(y, labels, fontsize=7.2)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Specimen-housing hardware (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.42, -0.32), ncol=4, fontsize=7, handlelength=1.2)
    n = json.loads((TABLES / "T4_summary.json").read_text())["n_habitats"]
    ax.set_title(f"What the public record says about each CFD input (n = {n}; * critical)", x=-0.45)
    style.save(fig, "F2_item_coverage")


def fig3_groups():
    m = pd.read_csv(TABLES / "T4a_habitat_meta.csv")
    s = json.loads((TABLES / "T4_summary.json").read_text())
    tests = {t["factor"]: t for t in s["tests"]}
    panels = [("hw_class", "Hardware class", ["plant", "rodent", "other_animal", "cell_microbe", "mixed"]),
              ("platform", "Flight platform",
               ["ISS", "Shuttle", "Free-flyer (Bion/Cosmos/Biosatellite)", "no mission record"]),
              ("coverage", "Catalogue coverage", ["SPLASH+registry", "registry only", "SPLASH only"])]
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 3.0), sharey=True, gridspec_kw={"width_ratios": [5, 4, 3]})
    rng = np.random.default_rng(1)
    for ax, (col, title, order) in zip(axes, panels):
        order = [o for o in order if (m[col] == o).sum() >= 3]
        for k, lev in enumerate(order):
            v = m.loc[m[col] == lev, "public_completeness"].values
            cc = m.loc[m[col] == lev, "hw_class"].map(CLASS_COLOR).values
            x = k + rng.uniform(-0.18, 0.18, len(v))
            ax.scatter(x, v, s=12, c=cc if col != "hw_class" else CLASS_COLOR[lev], alpha=0.85,
                       edgecolors="white", linewidths=0.4, zorder=3)
            ax.plot([k - 0.28, k + 0.28], [np.median(v)] * 2, color=INK, lw=1.6, zorder=4)
            ax.text(k, -0.07, f"n={len(v)}", ha="center", va="top", fontsize=6.5, color=INK2)
        lab = [CLASS_LABEL.get(o, o).replace("Other animal", "Other\nanimal").replace("Cell / microbe", "Cell /\nmicrobe").replace("Free-flyer (Bion/Cosmos/Biosatellite)", "Free-\nflyer").replace(
            "no mission record", "no mission\nrecord").replace("SPLASH+registry", "SPLASH +\nregistry")
            .replace("registry only", "registry\nonly").replace("SPLASH only", "SPLASH\nonly") for o in order]
        ax.set_xticks(range(len(order)), lab, fontsize=6.6)
        t = tests[col]
        ax.set_title(f"{title}\nKruskal-Wallis p = {t['p']:.1e}", fontsize=7.4, loc="left")
        ax.set_ylim(-0.12, 1.0)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("MI-CFD-HW completeness (0-1)")
    handles = [plt.Line2D([], [], marker="o", ls="", color=CLASS_COLOR[k], label=CLASS_LABEL[k], markersize=5)
               for k in CLASS_COLOR]
    fig.legend(handles=handles, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.06), fontsize=7)
    fig.subplots_adjust(bottom=0.27, wspace=0.16)
    style.save(fig, "F3_completeness_groups")


def fig4_usage():
    m = pd.read_csv(TABLES / "T4a_habitat_meta.csv")
    s = json.loads((TABLES / "T4_summary.json").read_text())
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    x = np.log10(m.n_osd_studies + 1)
    ax.scatter(x, m.public_completeness, s=16, c=m.hw_class.map(CLASS_COLOR), edgecolors="white",
               linewidths=0.5, zorder=3, alpha=0.9)
    med = s["completeness_median_public"]
    ax.axhline(med, color=MUTED, lw=0.8, ls="--")
    ax.text(np.log10(150), med + 0.015, f"median completeness {med:.2f}", ha="right", fontsize=6.5, color=INK2)
    lab = m[(m.n_osd_studies >= 5) | ((m.n_osd_studies > 0) & (m.public_completeness < med))]
    placed = []
    for r in lab.sort_values("public_completeness", ascending=False).itertuples():
        nm = SHORT.get(r.entity_id, r.canonical_name.split(";")[0].split("(")[0].strip()[:24])
        px, py = np.log10(r.n_osd_studies + 1), r.public_completeness
        ty = py
        for _ in range(40):  # nudge down until clear of earlier labels in the same x band
            if all(abs(ty - qy) > 0.035 or abs(px - qx) > 0.55 for qx, qy in placed):
                break
            ty -= 0.012
        placed.append((px, ty))
        ax.annotate(nm, (px, py), xytext=(px + 0.05, ty), textcoords="data", fontsize=6, color=INK2,
                    va="center", arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.4) if abs(ty - py) > 0.01 else None)
    ticks = [0, 1, 3, 10, 30, 100]
    ax.set_xticks(np.log10(np.array(ticks) + 1), [str(t) for t in ticks])
    ax.set_xlabel("OSDR studies linked to the hardware")
    ax.set_ylabel("MI-CFD-HW completeness (0-1)")
    r = s["spearman_studies_completeness_all"]
    ax.set_title(f"Use versus documentation (Spearman rho = {r['rho']:.2f}, p = {r['p']:.1e})")
    handles = [plt.Line2D([], [], marker="o", ls="", color=CLASS_COLOR[k], label=CLASS_LABEL[k], markersize=5)
               for k in CLASS_COLOR]
    ax.legend(handles=handles, loc="upper left", fontsize=6.5, ncol=1)
    ax.set_ylim(0, 1)
    style.save(fig, "F4_usage_vs_completeness")


def fig5_validation():
    it = pd.read_csv(TABLES / "T5_scorer_validation_items.csv")
    v = json.loads((TABLES / "T5_scorer_validation.json").read_text())
    it = it.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    y = np.arange(len(it))
    ax.hlines(y, it[["rater_agreement", "auto_vs_gold_agreement"]].min(axis=1) * 100,
              it[["rater_agreement", "auto_vs_gold_agreement"]].max(axis=1) * 100, color=MUTED, lw=1)
    ax.scatter(it.rater_agreement * 100, y, s=26, color=style.BLUE, label="rater A vs rater B", zorder=3)
    ax.scatter(it.auto_vs_gold_agreement * 100, y, s=26, color=style.VERMILION, marker="D",
               label="automated vs adjudicated gold", zorder=3)
    ax.set_yticks(y, [f"{r.item}  {r.label}" for r in it.itertuples()], fontsize=7)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Exact agreement on 12 randomly sampled habitats (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower left", fontsize=7)
    ax.set_title(f"Scorer validation: raters kappa_w = {v['rater_weighted_kappa']:.2f}; automated precision "
                 f"{v['auto_presence_precision']:.2f}, recall {v['auto_presence_recall']:.2f}", fontsize=8, x=-0.5)
    style.save(fig, "F5_scorer_validation")


def run():
    style.apply()
    fig1_funnel()
    fig2_items()
    fig3_groups()
    fig4_usage()
    fig5_validation()
    fig7_curated_gaps()
    fig8_where_and_feed()



def _short(name: str) -> str:
    import re
    base = name.split(" (")[0]
    if " - " in base and len(base.split(" - ")[-1]) <= 12:
        return base.split(" - ")[-1]
    paren = re.search(r"\(([^)]+)\)", name)
    if len(base) > 34 and paren:
        return paren.group(1).split(",")[0][:30]
    if len(base) > 34 and " - " in base:
        return base.split(" - ")[-1][:34]
    return base[:34]


def fig7_curated_gaps():
    """Critical-item matrix after literature curation (rows: hardware, grouped by tier)."""
    d = pd.read_csv(TABLES / "T6_curated_tiers.csv")
    order = {"A": 0, "B": 1, "C": 2}
    d = d.assign(_o=d.tier.map(order), _n=(d[["G1", "G2", "F1", "F2", "E1", "B1"]].sum(axis=1))) \
         .sort_values(["_o", "_n", "name"], ascending=[True, False, True]).reset_index(drop=True)
    items = ["G1", "G2", "F1", "F2", "E1", "B1"]
    labels = ["Enclosure\ndims", "Specimen\ncontainer", "Ventilation\nmode", "Airflow\nrate", "Temper-\nature",
              "Specimen\ntype"]
    fig, ax = plt.subplots(figsize=(5.4, 0.2 * len(d) + 1.4))
    for i, r in d.iterrows():
        y = len(d) - 1 - i
        for j, k in enumerate(items):
            if k == "F2" and r.F2_waived:
                ax.add_patch(plt.Rectangle((j, y), 0.92, 0.82, fc="white", ec=MUTED, lw=0.6, hatch="////"))
            else:
                ax.add_patch(plt.Rectangle((j, y), 0.92, 0.82, fc=LEVEL_COLOR[1.0] if r[k] else LEVEL_COLOR[0.0],
                                           ec="white", lw=0.8))
        ax.text(len(items) + 0.15, y + 0.41, r.tier, va="center", fontsize=7, fontweight="bold",
                color=style.VERMILION if r.tier == "A" else INK2)
        ax.text(-0.15, y + 0.41, _short(r["name"]), va="center", ha="right", fontsize=6.4, color=INK)
    ax.set_xlim(-0.1, len(items) + 0.6)
    ax.set_ylim(-0.2, len(d))
    ax.set_xticks(np.arange(len(items)) + 0.46, labels, fontsize=6.4)
    ax.xaxis.tick_top()
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(False)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=LEVEL_COLOR[1.0], label="sourced (verbatim quotation)"),
               plt.Rectangle((0, 0), 1, 1, fc=LEVEL_COLOR[0.0], label="not found"),
               plt.Rectangle((0, 0), 1, 1, fc="white", ec=MUTED, hatch="////", label="not applicable (sealed / passive)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.35, -0.01), ncol=3, fontsize=6.4,
              handlelength=1.2)
    ax.set_title("Critical CFD inputs after literature curation (tier at right)", fontsize=8.5, x=0.2, pad=26)
    style.save(fig, "F7_curated_gaps")


def fig8_where_and_feed():
    """Where bio-capable hardware flew (mission records) and how specimens are fed (evidenced modes)."""
    n = pd.read_csv(TABLES / "T2_counts.csv")
    plat = n[n.group == "platform (missions, bio-capable)"].sort_values("n")
    from .paths import DERIVED
    cls = pd.read_json(DERIVED / "classification.json")
    bio = cls[cls.bio_payload_capable]
    none = int((bio.platforms_from_missions.map(len) == 0).sum())
    plat = pd.concat([plat, pd.DataFrame([{"group": "", "key": "No mission record", "n": none}])])
    nut = n[n.group == "nutrient mode (habitats)"].copy()
    nice = {"agar_gel": "Agar / gel medium", "animal_food_water": "Animal food + drinking water",
            "aquatic_water_loop": "Aquatic water loop", "arcillite_substrate": "Arcillite / solid substrate",
            "hydroponic_aeroponic": "Hydroponic / aeroponic", "liquid_culture_medium": "Liquid culture medium",
            "water_only_wick": "Water / wick only", "none evidenced": "No evidence found"}
    nut["label"] = nut.key.map(nice)
    nut = pd.concat([nut[nut.key != "none evidenced"].sort_values("n"), nut[nut.key == "none evidenced"]])
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.9), gridspec_kw={"wspace": 0.9})
    ax = axes[0]
    ax.barh(plat.key.str.replace("Free-flyer (Bion/Cosmos/Biosatellite)", "Free-flyer (Bion/Cosmos)"), plat.n,
            color=[MUTED if k == "No mission record" else style.BLUE for k in plat.key], height=0.6)
    for y, v in enumerate(plat.n):
        ax.text(v + 0.6, y, str(v), va="center", fontsize=7)
    ax.set_xlabel(f"Bio-capable hardware (n = {len(bio)}) with a\nregistry mission on this platform")
    ax.set_title("Where it flew", fontsize=8.5)
    ax.grid(axis="y", visible=False)
    ax = axes[1]
    cols = [MUTED if k == "none evidenced" else style.GREEN for k in nut.key]
    ax.barh(nut.label, nut.n, color=cols, height=0.6)
    for y, v in enumerate(nut.n):
        ax.text(v + 0.6, y, str(v), va="center", fontsize=7)
    hab = int(n[(n.group == "bio") & (n.key.str.startswith("specimen habitats"))].n.iloc[0])
    ax.set_xlabel(f"Specimen habitats (n = {hab}); a habitat\ncan use more than one mode")
    ax.set_title("How specimens are fed and watered", fontsize=8.5)
    ax.grid(axis="y", visible=False)
    style.save(fig, "F8_where_and_feed")


if __name__ == "__main__":
    run()
