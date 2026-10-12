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
    for slug, meshes in CAMPAIGN:
        if mesh not in meshes:
            continue
        for g in ("0g", "1g"):
            c = RUNS / f"{slug}_{g}_{mesh}"
            if not (c / "postProcessing").exists():
                continue
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
                "H2O_excess_mmol_mol": m.get(f"{pre}:H2O:final_excess"),
                "T_excess_K": m.get(f"{pre}:T:final_excess"),
                "age_of_air_s": m.get(f"{pre}:AoA:final_excess"),
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
            })
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / f"T9_cfd_results_{mesh}.csv", index=False)
    return df


def comparison(df: pd.DataFrame, mesh: str):
    style.apply()
    qs = [("CO2_excess_ppm", "Specimen-zone CO$_2$ excess (ppm)"), ("T_excess_K", "Specimen-zone T excess (K)"),
          ("age_of_air_s", "Specimen-zone age of air (s)")]
    models = [m for m in df.model.unique()]
    fig, axes = plt.subplots(1, len(qs), figsize=(7.4, 0.42 * len(models) + 1.2), sharey=True)
    y = np.arange(len(models))[::-1]
    for ax, (q, lab) in zip(axes, qs):
        for g, off in (("0g", 0.12), ("1g", -0.12)):
            v = [df[(df.model == m) & (df.gravity == g)][q].iloc[0] if len(df[(df.model == m) & (df.gravity == g)]) else np.nan
                 for m in models]
            ax.scatter(v, y + off, color=GRAVITY_COLOR[g], s=26, label=g, zorder=3)
        ax.set_title(lab, fontsize=7.6)
        ax.grid(axis="y", visible=False)
        ax.axvline(0, color=INK2, lw=0.5)
    axes[0].set_yticks(y, [LABEL.get(m, m) for m in models], fontsize=7)
    axes[0].legend(fontsize=7, loc="lower right")
    fig.suptitle("Flight (0 g) versus ground control (1 g) in the same hardware", x=0.01, ha="left", fontsize=9)
    fig.tight_layout()
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
    for slug, meshes in CAMPAIGN:
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
    df = table(a.mesh)
    if len(df):
        comparison(df, a.mesh)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
