#!/usr/bin/env python3
"""Build the GitHub Pages site in docs/ from the results.

The page text lives in site/index.template.html. Every number in it is a
{{hwName}} placeholder for a macro in results/macros.tex (the same numbers the
manuscript quotes), and every table and the hardware explorer data are read from
results/tables. The build fails on an unknown placeholder, so no number on the page
can be typed by hand. Figures, animations and the manuscript builds are copied into
docs/. The CoSE theme stylesheet and logo are loaded from the shared hosted kit; the
CoSE navigation rail (theme.js / sites.js) is deliberately not loaded.
"""
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

root = Path(__file__).resolve().parents[1]
SITE, DOCS = root / "site", root / "docs"
TABLES, FIGS = root / "results" / "tables", root / "results" / "figures"
REPO = "https://github.com/dr-richard-barker/Hardware_OSDR_review"

# CFD runs shown in the model viewer: (model slug, geometry sheet slug)
RUNS = [("mds", "mds"), ("aph", "aph"), ("aph_fanmax", "aph_fanmax"),
        ("vented_fly_box_vent20", "vented_fly_box_vent20"), ("vented_fly_box_vent60", "vented_fly_box_vent60"),
        ("aqh", "aqh")]
ANIM_FIELD = {"aqh": "AoA"}           # animated scalar per model (default CO2)
FIGURES = ["F1_catalogue_funnel", "F2_item_coverage", "F3_completeness_groups", "F4_usage_vs_completeness",
           "F5_scorer_validation", "F6_cfd_comparison_medium", "F7_curated_gaps", "F8_where_and_feed"]

LOCATION = {"Free_flyer_Bion_Cosmos": "Free-flyer / Bion / Cosmos", "Ground_facility": "Ground facility",
            "ISS_Columbus": "ISS Columbus", "ISS_EXPRESS_rack": "ISS EXPRESS rack", "ISS_JEM_Kibo": "ISS Kibo",
            "ISS_US_lab_MSG": "ISS US Lab / MSG", "ISS_external": "ISS external", "ISS_general": "ISS",
            "Lunar_or_beyond": "Lunar or beyond", "Mir": "Mir", "Shuttle_middeck": "Shuttle middeck",
            "Spacelab": "Spacelab", "Suborbital": "Suborbital"}
NUTRIENT = {"agar_gel": "agar / gel", "animal_food_water": "food bar + water", "aquatic_water_loop": "aquatic water loop",
            "arcillite_substrate": "arcillite substrate", "hydroponic_aeroponic": "hydroponic / aeroponic",
            "liquid_culture_medium": "liquid culture medium", "water_only_wick": "water only / wick"}
ORGANISM = {"aquatic_vertebrate": "aquatic vertebrate", "avian": "avian", "cell_tissue": "cells / tissue",
            "invertebrate": "invertebrate", "microbe": "microbe", "plant": "plant", "primate": "primate",
            "rodent": "rodent"}


def macros() -> dict:
    out = {}
    for name, val in re.findall(r"\\newcommand\{\\(hw\w+)\}\{(.*)\}\s*$", (root / "results/macros.tex").read_text(),
                                re.M):
        val = val.replace("{,}", ",")
        val = re.sub(r"\\times10\^\{(-?\d+)\}", lambda m: f"&thinsp;×&thinsp;10<sup>{m.group(1)}</sup>", val)
        out[name] = val.replace("-", "−")
    return out


def esc(x) -> str:
    return html.escape(str(x))


def split(v) -> list:
    return [s.strip() for s in str(v).split(";") if s.strip()] if isinstance(v, str) else []


def fmt(x, nd=2) -> str:
    return "–" if pd.isna(x) else f"{x:,.{nd}f}".replace("-", "−")


def table_items() -> str:
    it = pd.read_csv(TABLES / "T4c_item_missingness.csv")
    rows = []
    for r in it.itertuples():
        crit = '<span class="tag">critical</span>' if r.critical else ""
        rows.append(f"<tr><td><code>{esc(r.item)}</code></td><td>{esc(r.label)} {crit}</td>"
                    f'<td class="num">{100 * r.quantitative:.0f}%</td><td class="num">{100 * r.splash_quantitative:.0f}%</td>'
                    f'<td class="num">{100 * r.absent:.0f}%</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Item</th><th>What the CFD model needs</th>'
            '<th class="num">Quantitative, all public sources</th><th class="num">Quantitative, SPLASH alone</th>'
            '<th class="num">Absent</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def table_verify() -> str:
    v = pd.read_csv(TABLES / "T8_verification_cavity.csv")
    rows = []
    for r in v.itertuples():
        exp = int(round(math.log10(r.Ra)))
        rows.append(f"<tr><td>10<sup>{exp}</sup></td><td class='num'>{r.Nu_64:.3f}</td><td class='num'>{r.Nu_96:.3f}</td>"
                    f"<td class='num'>{r.Nu_128:.3f}</td><td class='num'>{r.Nu_extrapolated:.3f}</td>"
                    f"<td class='num'>{r.ref_Hortmann:.3f}</td><td class='num'>{fmt(r.err_ext_vs_Hortmann_pct)}</td>"
                    f"<td class='num'>{fmt(r.p_observed)}</td><td>{esc(r.convergence)}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>Ra</th><th class="num">Nu 64²</th><th class="num">Nu 96²</th>'
            '<th class="num">Nu 128²</th><th class="num">Nu extrapolated</th><th class="num">Hortmann et al. 1990</th>'
            '<th class="num">Error (%)</th><th class="num">Observed order p</th><th>Convergence</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def table_cfd() -> str:
    t = pd.read_csv(TABLES / "T9_cfd_results_medium.csv")
    rows = []
    for r in t.itertuples():
        co2 = "–" if pd.isna(r.CO2_excess_ppm) else f"{fmt(r.CO2_excess_ppm)} ± {fmt(r.CO2_late_sd_ppm)}"
        bal = "–" if pd.isna(r.CO2_balance_rel_imbalance) else f"{100 * abs(r.CO2_balance_rel_imbalance):.2f}%"
        rows.append(f"<tr><td>{esc(r.label)}</td><td>{esc(r.gravity.replace('g', '&nbsp;g'))}</td><td>{esc(r.medium)}</td>"
                    f"<td>{esc(r.zone)}</td><td class='num'>{co2}</td><td class='num'>{fmt(r.T_excess_K)}</td>"
                    f"<td class='num'>{fmt(r.age_of_air_s)} ± {fmt(r.age_late_sd_s)}</td>"
                    f"<td class='num'>{fmt(r.Re_inlet, 0)}</td><td class='num'>{bal}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>Hardware</th><th>g</th><th>Medium</th><th>Zone</th>'
            '<th class="num">CO₂ excess (ppm)</th><th class="num">ΔT (K)</th><th class="num">Age (s)</th>'
            '<th class="num">Re inlet</th><th class="num">CO₂ balance error</th></tr></thead><tbody>'
            + "".join(rows).replace("&amp;nbsp;", "&nbsp;") + "</tbody></table></div>")


def table_curated() -> str:
    c = pd.read_csv(TABLES / "T6_curated_tiers.csv").sort_values(["tier", "name"])
    rows = []
    for r in c.itertuples():
        miss = esc(r.missing) if isinstance(r.missing, str) else "none"
        rows.append(f"<tr><td>{esc(r.name)}</td><td><span class='tier tier-{esc(r.tier)}'>{esc(r.tier)}</span></td>"
                    f"<td>{miss}</td><td class='num'>{r.n_sourced}/{r.n_parameters}</td></tr>")
    return ('<div class="tbl tall"><table><thead><tr><th>Hardware</th><th>Tier</th><th>Missing critical items</th>'
            '<th class="num">Sourced / sought</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def _num(x: float) -> str:
    return f"{x:,.0f}" if x >= 100 else f"{x:.3g}"


def anim_caption(m: str, field: str, fname: str) -> str:
    """Time window and production-run check for an animation, from the model file and T10."""
    a = (yaml.safe_load((root / "models" / f"{m}.yaml").read_text()) or {}).get("animation")
    if not a:
        return f"Four-dimensional record: {fname} on a mid-plane slice through time (medium mesh)."
    txt = (f"Four-dimensional record: {fname} on the vertical mid-plane from t&nbsp;=&nbsp;0 to "
           f"{a['end_time_s']:g}&nbsp;s, one frame every {a['write_every_s']:g}&nbsp;s, from a dedicated "
           f"animation run on the production mesh.")
    t10 = TABLES / "T10_animation_consistency.csv"
    if t10.exists():
        c = pd.read_csv(t10)
        c = c[(c.model == m) & c.quantity.str.endswith(f":{field}")]
        if len(c):
            where = "domain-average" if c.quantity.str.startswith("domainAvg").all() else "specimen-zone"
            what = f"the {fname} excess" if field == "CO2" else f"the mean {fname}"
            pct = c.rel_diff_of_excess_pct.max()
            agree = ("matches the production run to better than 0.01%" if pct < 0.01 else
                     f"agrees with the production run within {pct:.2g}%")
            txt += (f" Its {where} mean over t&nbsp;=&nbsp;{_num(c.window_start_s.min())}–{_num(c.window_end_s.max())}&nbsp;s "
                    f"{agree} of {what}.")
    return txt


def model_viewer() -> str:
    t = pd.read_csv(TABLES / "T9_cfd_results_medium.csv").drop_duplicates("model").set_index("model")
    tabs, panels = [], []
    for i, (m, ortho) in enumerate(RUNS):
        label = t.loc[m, "label"]
        sel = "true" if i == 0 else "false"
        tabs.append(f'<button role="tab" id="tab-{m}" aria-controls="panel-{m}" aria-selected="{sel}" '
                    f'tabindex="{0 if i == 0 else -1}">{esc(label)}</button>')
        field = ANIM_FIELD.get(m, "CO2")
        fname = {"CO2": "CO₂", "AoA": "age of water"}[field]
        hidden = "" if i == 0 else " hidden"
        panels.append(
            f'<div class="mpanel" role="tabpanel" id="panel-{m}" aria-labelledby="tab-{m}"{hidden}>'
            f'<div class="mgrid"><figure><img loading="lazy" src="assets/fig/ortho_{ortho}.png" '
            f'alt="Orthographic drawing of the {esc(label)} CFD geometry"><figcaption>Geometry: front, side and plan '
            f'elevations and isometric view, with inlets, outlets, vents and the specimen zone. '
            f'<a href="assets/fig/ortho_{ortho}.png">Full size</a></figcaption></figure>'
            f'<figure><video controls loop muted playsinline preload="none" '
            f'poster="assets/fig/anim_{m}_medium_{field}_poster.png" src="assets/fig/anim_{m}_medium_{field}.mp4" '
            f'aria-label="Animation of {fname} on a mid-plane slice, {esc(label)}"></video><figcaption>'
            f'{anim_caption(m, field, fname)}</figcaption></figure></div>'
            f'<figure><img loading="lazy" src="assets/fig/fields_{m}_medium.png" alt="Field slices for {esc(label)}">'
            f'<figcaption>Field slices at the end of the run. <a href="assets/fig/fields_{m}_medium.png">Full size</a>'
            f'</figcaption></figure>'
            f'<figure><img loading="lazy" src="assets/fig/card_{m}_medium.png" alt="Specimen-zone time series for {esc(label)}">'
            f'<figcaption>Specimen-zone time series, flight (0&nbsp;g) and ground control (1&nbsp;g) where both were run.'
            f'</figcaption></figure></div>')
    return ('<div class="mtabs" role="tablist" aria-label="Modelled hardware">' + "".join(tabs) + "</div>"
            + "".join(panels))


def habitats() -> list:
    t1 = pd.read_csv(TABLES / "T1_hardware_catalogue.csv")
    t3 = pd.read_csv(TABLES / "T3_sufficiency_scores.csv").set_index("entity_id")
    t6 = pd.read_csv(TABLES / "T6_curated_tiers.csv").set_index("entity_id")
    out = []
    for r in t1[t1.specimen_habitat].itertuples():
        s = t3.loc[r.entity_id]
        cur = t6.loc[r.entity_id] if r.entity_id in t6.index else None
        out.append({
            "id": r.entity_id, "n": r.canonical_name,
            "org": [ORGANISM.get(o, o) for o in split(r.organism_classes_all)],
            "loc": sorted({LOCATION.get(o, o) for o in split(r.location_classes_text)}),
            "nut": [NUTRIENT.get(o, o) for o in split(r.nutrient_modes)],
            "st": int(r.n_osd_studies), "c": round(float(s.public_completeness), 2),
            "cs": round(float(s.splash_completeness), 2), "t": s.public_tier,
            "b": s.public_blocking if isinstance(s.public_blocking, str) else "",
            "ct": None if cur is None else cur.tier,
            "cm": "" if cur is None or not isinstance(cur.missing, str) else cur.missing,
            "yr": None if pd.isna(r.first_launch) else int(r.first_launch),
            "status": r.splash_status if isinstance(r.splash_status, str) else ""})
    return sorted(out, key=lambda d: (-d["c"], d["n"].lower()))


def main():
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "assets/fig").mkdir(parents=True)
    (DOCS / "assets/data").mkdir()
    (DOCS / "paper").mkdir()
    (DOCS / ".nojekyll").write_text("")
    for f in ("site.css", "site.js"):
        shutil.copy2(SITE / f, DOCS / "assets" / f)
    names = FIGURES + [f"ortho_{o}" for _, o in RUNS] + [f"{k}_{m}_medium" for m, _ in RUNS for k in ("fields", "card")]
    for n in names:
        shutil.copy2(FIGS / f"{n}.png", DOCS / "assets/fig" / f"{n}.png")
    for m, _ in RUNS:
        for n in (f"anim_{m}_medium_{ANIM_FIELD.get(m, 'CO2')}.mp4", f"anim_{m}_medium_{ANIM_FIELD.get(m, 'CO2')}_poster.png"):
            shutil.copy2(FIGS / n, DOCS / "assets/fig" / n)
    for f in ("manuscript.pdf", "manuscript.html", "supplement.pdf"):
        shutil.copy2(root / "latex/output" / f, DOCS / "paper" / f)
    hab = habitats()
    (DOCS / "assets/data/habitats.json").write_text(json.dumps(hab, ensure_ascii=False, separators=(",", ":")))

    m = macros()
    m.update({"TABLE_ITEMS": table_items(), "TABLE_VERIFY": table_verify(), "TABLE_CFD": table_cfd(),
              "TABLE_CURATED": table_curated(), "MODEL_VIEWER": model_viewer(), "REPO": REPO,
              "N_EXPLORER": str(len(hab))})
    page = (SITE / "index.template.html").read_text()
    unknown = sorted(set(re.findall(r"\{\{(\w+)\}\}", page)) - set(m))
    if unknown:
        sys.exit(f"build_site: unknown placeholder(s): {', '.join(unknown)}")
    page = re.sub(r"\{\{(\w+)\}\}", lambda x: m[x.group(1)], page)
    (DOCS / "index.html").write_text(page)
    n = sum(1 for p in DOCS.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in DOCS.rglob("*") if p.is_file()) / 1e6
    print(f"docs/: {n} files, {size:.1f} MB, {len(hab)} habitats in the explorer")


if __name__ == "__main__":
    main()
