"""Stage 7b - cross-hardware CFD results: metrics table, environment cards, comparison, 4-D exports.

    python -m hwreview.results [--mesh medium] [--no-vtk] [--no-anim]

T9_cfd_results.csv   one row per model x gravity: specimen-zone excess CO2 / H2O / T over
                     the supply (or initial) state, zone age of air, max |U|, Re, Ri,
                     transient CO2-balance imbalance
F6_cfd_comparison    0 g vs 1 g specimen-zone excesses across hardware
card_<model>         environment card: zone time series in 0 g and 1 g
results/fields/      timeseries CSV per run; VTK time series (tar.gz) per medium run
"""
from __future__ import annotations

import argparse
import json
import tarfile

import numpy as np
import pandas as pd

from . import post, style
from .campaign import CAMPAIGN
from .paths import FIELDS, RUNS, TABLES
from .style import GRAVITY_COLOR, INK2, plt

LABEL = {"aph": "APH (PH-04 set-points)", "aph_fanmax": "APH (fan 1.5 m/s)", "mds": "MDS mouse cage",
         "vented_fly_box_vent20": "Vented Fly Box (20 mm vents)", "vented_fly_box_vent60": "Vented Fly Box (60 mm vents)",
         "aqh": "AQH aquarium (water)"}


def _zone(meta):
    z = list((meta.get("sources_total") or {}).keys())
    return z[0] if z else None


def card(slug: str, mesh: str):
    style.apply()
    ts = {}
    for g in ("0g", "1g"):
        f = FIELDS / f"timeseries_{slug}_{g}_{mesh}.csv"
        if f.exists():
            ts[g] = pd.read_csv(f)
    if not ts:
        return
    meta = json.loads((RUNS / f"{slug}_0g_{mesh}" / "case_meta.json").read_text())
    z = _zone(meta)
    init = meta["initial"]
    T0 = init["T_C"] + 273.15
    panels = []
    for fld, base, lab in (("CO2", init.get("CO2_ppm"), "CO$_2$ excess (ppm)"),
                           ("H2O", init.get("H2O_mmol_mol"), "H$_2$O excess (mmol mol$^{-1}$)"),
                           ("T", T0, "temperature excess (K)"), ("AoA", 0.0, "age of air (s)")):
        col = f"zone_{z}:{fld}" if z else f"domainAvg:{fld}"
        if base is not None and all(col in d for d in ts.values()):
            panels.append((col, base, lab))
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(2.6 * len(panels), 2.4), squeeze=False)
    for ax, (col, base, lab) in zip(axes[0], panels):
        for g, d in ts.items():
            ax.plot(d.time, d[col] - base, color=GRAVITY_COLOR[g], lw=1.6, label=g)
        ax.set_xlabel("time (s)")
        ax.set_title(lab, fontsize=7.5)
    axes[0][0].legend(fontsize=7)
    where = f"specimen zone '{z}'" if z else "domain average"
    fig.suptitle(f"{LABEL.get(slug, slug)} - {where}, {mesh} mesh", x=0.01, ha="left", fontsize=9)
    fig.tight_layout()
    style.save(fig, f"card_{slug}_{mesh}")


def inlet_reynolds(case, slug: str, meta: dict) -> float | None:
    """Re = U_mean D_h / nu at each inlet: U_mean from the solved flow rate and patch area,
    D_h = 4A/P of the specified (rectangular) opening. Returns the largest over inlets."""
    from . import geometry
    nu = (meta["physics"].get("water") or meta["physics"]["air"])["nu"]
    best = None
    for o in geometry.load(slug).openings:
        if o.get("role") != "inlet":
            continue
        f = sorted((case / "postProcessing" / f"flow_{o['name']}").glob("*/surfaceFieldValue.dat"),
                   key=lambda q: float(q.parent.name))
        if not f:
            continue
        txt = f[-1].read_text()
        area = float(txt.split("Area")[1].split(":")[1].split()[0])
        q = abs(float(txt.strip().splitlines()[-1].split()[1]))
        a, b = (x / 1000 for x in o["size"])
        dh = 4 * a * b / (2 * (a + b))
        re_ = q / area * dh / nu
        best = re_ if best is None else max(best, re_)
    return best


def nominal_residence(case, ts) -> float | None:
    """Mesh volume / total inflow (s) for cases with inlets; None for sealed or passive cases."""
    import re
    flows = [c for c in ts.columns if c.startswith("flow_") and c.endswith(":phi")]
    q_in = -sum(min(0.0, float(ts[c].iloc[-1])) for c in flows)
    if q_in <= 0:
        return None
    v = float(re.search(r"Total volume = ([0-9.eE+-]+)", (case / "log.checkMesh").read_text()).group(1).rstrip("."))
    return v / q_in


def solutal_ra(m: dict, meta: dict, pre: str):
    dco2 = m.get(f"{pre}:CO2:final_excess")
    if dco2 is None or meta.get("medium") == "water":
        return None
    air = meta["physics"]["air"]
    from . import physics
    m_co2, m_air = physics.molar_mass_g_mol("CO2"), physics.molar_mass_g_mol("Air")
    drho = abs(dco2) * 1e-6 * (m_co2 - m_air) / m_air
    L = m["L_char_m"]
    return 9.80665 * drho * L ** 3 / (air["nu"] * meta["physics"]["D_CO2_m2_s"])


def table(mesh: str) -> pd.DataFrame:
    rows = []
    for slug, meshes, _g in CAMPAIGN:
        if mesh not in meshes:
            continue
        for g in ("0g", "1g"):
            c = RUNS / f"{slug}_{g}_{mesh}"
            from .campaign import done
            if not (c.exists() and done(c)):
                continue                      # only complete runs enter the results table
            meta = json.loads((c / "case_meta.json").read_text())
            ts = post.timeseries(c)
            m = post.metrics(c, ts)
            z = _zone(meta)
            pre = f"zone_{z}" if z else "domainAvg"
            rows.append({
                "model": slug, "label": LABEL.get(slug, slug), "gravity": g, "medium": meta.get("medium", "air"),
                "t_end_s": m["t_end_s"],
                "zone": z or "domain",
                "CO2_excess_ppm": m.get(f"{pre}:CO2:final_excess"),
                "CO2_late_sd_ppm": m.get(f"{pre}:CO2:late_sd"),
                "H2O_excess_mmol_mol": m.get(f"{pre}:H2O:final_excess"),
                "T_excess_K": m.get(f"{pre}:T:final_excess"),
                "T_late_sd_K": m.get(f"{pre}:T:late_sd"),
                "age_of_air_s": m.get(f"{pre}:AoA:final_excess"),
                "age_late_sd_s": m.get(f"{pre}:AoA:late_sd"),
                "domain_CO2_excess_ppm": m.get("domainAvg:CO2:final_excess"),
                "U_max_m_s": m.get("U_max_late_m_s"), "Re": m.get("Re"), "Re_inlet": inlet_reynolds(c, slug, meta),
                "Ri_1g": m.get("Ri_1g"),
                "Ra_1g": m.get("Ra_1g"),
                "CO2_balance_rel_imbalance": (m.get("conservation_CO2") or {}).get("rel_imbalance"),
                "t90_CO2_s": m.get(f"{pre}:CO2:t90_s"),
                # solutal buoyancy omitted by the Boussinesq-T solver: its Rayleigh number from the simulated
                # CO2 excess (drho/rho = dx (M_CO2 - M_air)/M_air; molar masses from CoolProp)
                "Ra_solutal_CO2_1g": solutal_ra(m, meta, pre),
                "Ra_thermal_1g": m.get("Ra_1g"),
                "nominal_residence_s": nominal_residence(c, ts),
            })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / f"T9_cfd_results_{mesh}.csv", index=False)
    return df


def comparison(df: pd.DataFrame, mesh: str):
    style.apply()
    qs = [("CO2_excess_ppm", "CO2_late_sd_ppm", "CO$_2$ excess (ppm)", "linear"),
          ("T_excess_K", "T_late_sd_K", "Temperature excess (K)", "linear"),
          ("age_of_air_s", "age_late_sd_s", "Age of air (s, log scale)", "log")]
    models = list(df.model.unique())
    labels = [LABEL.get(m, m).replace(" (water)", ", water") + (" (whole volume)" if (df[df.model == m].zone == "domain").all()
                                                                 else "") for m in models]
    fig, axes = plt.subplots(1, len(qs), figsize=(7.6, 0.46 * len(models) + 1.3), sharey=True,
                             gridspec_kw={"wspace": 0.12})
    y = np.arange(len(models))[::-1]
    for ax, (q, sdq, lab, scale) in zip(axes, qs):
        for g, off in (("0g", 0.13), ("1g", -0.13)):
            for yi, m in zip(y, models):
                r = df[(df.model == m) & (df.gravity == g)]
                if not len(r) or pd.isna(r[q].iloc[0]):
                    continue
                v = float(r[q].iloc[0])
                sd = float(r[sdq].iloc[0]) if sdq in r and pd.notna(r[sdq].iloc[0]) else 0.0
                if scale == "log" and v <= 0:
                    continue
                ax.errorbar(v, yi + off, xerr=sd if sd > 0 else None, fmt="o", ms=4.5, color=GRAVITY_COLOR[g],
                            ecolor=GRAVITY_COLOR[g], elinewidth=1, capsize=2, zorder=3)
                txt = "0" if (q == "T_excess_K" and abs(v) < 1e-4) else f"{v:.3g}"   # round-off-level T excess
                ax.annotate(txt, (v, yi + off), xytext=(5, 0), textcoords="offset points", va="center",
                            fontsize=5.8, color=INK2)
        ax.set_xscale(scale)
        ax.set_title(lab, fontsize=7.6)
        ax.grid(axis="y", visible=False)
        if scale == "linear":
            ax.axvline(0, color=INK2, lw=0.5)
        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi + 0.18 * (hi - lo) if scale == "linear" else hi * 3)
    axes[0].set_yticks(y, labels, fontsize=7)
    handles = [plt.Line2D([], [], marker="o", ls="", color=GRAVITY_COLOR[g], label=lab_)
               for g, lab_ in (("0g", "flight (0 g)"), ("1g", "ground control (1 g)"))]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=7, bbox_to_anchor=(0.55, -0.02))
    fig.suptitle("Specimen-zone environment at the end of each run (bars: temporal s.d.)", x=0.01, ha="left",
                 fontsize=9)
    fig.subplots_adjust(bottom=0.16)
    style.save(fig, f"F6_cfd_comparison_{mesh}")


def export_vtk(slug: str, mesh: str):
    for g in ("0g", "1g"):
        c = RUNS / f"{slug}_{g}_{mesh}"
        if not (c / "postProcessing").exists():
            continue
        if not (c / "VTK").exists():
            post.to_vtk(c)
        FIELDS.mkdir(parents=True, exist_ok=True)
        with tarfile.open(FIELDS / f"vtk_{c.name}.tar.gz", "w:gz") as tf:
            tf.add(c / "VTK", arcname=f"{c.name}/VTK")
            tf.add(c / "case_meta.json", arcname=f"{c.name}/case_meta.json")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", default="medium")
    ap.add_argument("--no-vtk", action="store_true")
    ap.add_argument("--no-anim", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    for slug, meshes, _g in CAMPAIGN:
        if a.only and slug not in a.only.split(","):
            continue
        if a.mesh not in meshes or not (RUNS / f"{slug}_0g_{a.mesh}" / "postProcessing").exists():
            continue
        post.run(slug, a.mesh, vtk=False)
        card(slug, a.mesh)
        if not a.no_anim:
            meta = json.loads((RUNS / f"{slug}_0g_{a.mesh}" / "case_meta.json").read_text())
            post.animate(slug, a.mesh, "CO2" if "CO2" in meta.get("scalars", []) else "AoA")
        if not a.no_vtk:
            export_vtk(slug, a.mesh)
    if not a.no_anim:
        post.animation_consistency([s for s, meshes, _ in CAMPAIGN if a.mesh in meshes], a.mesh)
    df = table(a.mesh)
    if len(df):
        comparison(df, a.mesh)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
