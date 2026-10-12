"""Stage 7a - post-process hardware runs: time series, metrics, 4-D fields, slices, animations.

    python -m hwreview.post <slug> [--mesh medium] [--vtk] [--anim]

Per run (runs/<slug>_<g>_<mesh>):
  timeseries.csv   zone/domain volume averages and outlet flux-weighted values vs time
  metrics.json     plateau excess CO2/H2O/T over the supply/initial state, time to 90 %
                   of the final excess, max |U|, dimensionless groups, conservation check
  VTK/             foamToVTK time series of U, T, CO2, H2O (the 4-D field record)
Figures: results/figures/fields_<slug>_<mesh>.png (0 g vs 1 g mid-plane slices) and
results/figures/anim_<slug>_<mesh>.mp4.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from . import foam, physics, style
from .paths import FIELDS, FIGURES, RUNS, TABLES
from .style import INK2, plt


def _read_dat(p: Path) -> pd.DataFrame:
    lines = p.read_text().splitlines()
    hdr = [ln for ln in lines if ln.startswith("#")][-1].lstrip("#").split()
    rows = [ln.split() for ln in lines if ln and not ln.startswith("#")]
    df = pd.DataFrame(rows, columns=hdr[:len(rows[0])] if rows else hdr).apply(pd.to_numeric, errors="coerce")
    return df.rename(columns={hdr[0]: "time"})


def _strip_op(c: str) -> str:
    m = re.match(r"^(?:volAverage|weightedAverage|sum)\((.*)\)$", c)
    return m.group(1) if m else c


def timeseries(case: Path) -> pd.DataFrame:
    pp = case / "postProcessing"
    out = None
    for d in sorted(pp.iterdir()):
        if not (d.name.startswith("zone_") or d.name.startswith("flux_") or d.name.startswith("flow_")
                or d.name == "domainAvg"):
            continue
        files = sorted(d.glob("*/*.dat"), key=lambda f: float(f.parent.name))
        if not files:
            continue
        df = pd.concat([_read_dat(f) for f in files]).drop_duplicates("time", keep="last")
        df = df.rename(columns={c: f"{d.name}:{_strip_op(c)}" for c in df.columns if c != "time"})
        out = df if out is None else pd.merge_asof(out.sort_values("time"), df.sort_values("time"), on="time",
                                                  direction="nearest")
    return out


def metrics(case: Path, ts: pd.DataFrame) -> dict:
    meta = json.loads((case / "case_meta.json").read_text())
    init = meta["initial"]
    T0 = init["T_C"] + 273.15
    res = {"case": case.name, "t_end_s": float(ts.time.max())}
    for col in ts.columns:
        if not col.startswith("zone_") and not col.startswith("domainAvg"):
            continue
        base = {"CO2": init["CO2_ppm"], "H2O": init["H2O_mmol_mol"], "T": T0}[col.split(":")[1]]
        y = ts[col].values - base
        final = float(np.mean(y[ts.time >= 0.9 * ts.time.max()]))
        res[f"{col}:final_excess"] = final
        if abs(final) > 1e-12:
            k = np.argmax(np.abs(y) >= 0.9 * abs(final))
            res[f"{col}:t90_s"] = float(ts.time.values[k])
    mm = case / "postProcessing" / "minmax"
    umax = []
    for f in sorted(mm.glob("*/fieldMinMax.dat"), key=lambda f: float(f.parent.name)):
        for ln in f.read_text().splitlines():
            if ln.startswith("#"):
                continue
            parts = ln.split("\t")
            parts = [x.strip() for x in parts if x.strip()]
            if len(parts) >= 6 and parts[1] == "mag(U)":
                umax.append((float(parts[0]), float(parts[5])))
    if umax:
        tu = np.array(umax)
        res["U_max_m_s"] = float(tu[:, 1].max())
        res["U_max_late_m_s"] = float(tu[tu[:, 0] >= 0.9 * tu[:, 0].max(), 1].mean())
    # dimensionless groups
    air = meta["physics"]["air"]
    lo = np.array(meta["geometry"].get("domain_volume_mm3", 0)) ** (1 / 3) / 1000
    L = float(lo)
    nu, kappa = air["nu"], air["k"] / (air["rho"] * air["cp"])
    U = res.get("U_max_late_m_s") or 0.0
    dT = abs(res.get("domainAvg:T:final_excess", 0.0))
    for z in [c for c in res if c.endswith(":T:final_excess") and c.startswith("zone_")]:
        dT = max(dT, abs(res[z]))
    g = 9.80665
    res.update({"L_char_m": L, "Re": U * L / nu, "Pe_CO2": U * L / meta["physics"]["D_CO2_m2_s"],
                "Ra_1g": g * air["beta"] * dT * L ** 3 / (nu * kappa),
                "Gr_1g": g * air["beta"] * dT * L ** 3 / nu ** 2})
    res["Ri_1g"] = res["Gr_1g"] / res["Re"] ** 2 if res["Re"] > 0 else None
    # conservation: S = Q_out (c_out - c_in) + V d<c>/dt (transient CO2 balance, ppm m3 s-1),
    # evaluated over the last 20 % of the run; sealed cases have Q_out = 0.
    src = meta.get("sources_total") or {}
    S_co2 = sum(v["CO2_mol_s"] for v in src.values())
    vol_m = re.search(r"Total volume = ([0-9.eE+-]+)", (case / "log.checkMesh").read_text())
    V = float(vol_m.group(1).rstrip(".")) if vol_m else None
    if S_co2 and V and "domainAvg:CO2" in ts:
        c_air = air["molar_density"]
        S = S_co2 / c_air * 1e6
        late = ts[ts.time >= 0.8 * ts.time.max()]
        t, cavg = late.time.values, late["domainAvg:CO2"].values
        acc = V * np.polyfit(t, cavg, 1)[0] if len(t) > 3 else 0.0
        outflow = 0.0
        for f in [c for c in ts.columns if c.startswith("flow_") and c.endswith(":phi")]:
            nm = f.split(":")[0].replace("flow_", "")
            q = late[f].values
            cf = late.get(f"flux_{nm}:CO2")
            if cf is not None:
                outflow += float(np.mean(q * (cf.values - init["CO2_ppm"])))
        res["conservation_CO2"] = {"source_ppm_m3_s": S, "outflow_ppm_m3_s": outflow,
                                   "accumulation_ppm_m3_s": float(acc), "mesh_volume_m3": V,
                                   "rel_imbalance": float((S - outflow - acc) / S)}
    return res


def to_vtk(case: Path):
    foam.run(case, ["foamToVTK -fields '(U T CO2 H2O)' -noFaceZones -noPointValues"])


def _read_slice(case: Path, y_m: float | None):
    import pyvista as pv
    (case / "case.foam").touch()
    r = pv.POpenFOAMReader(str(case / "case.foam"))
    t = r.time_values[-1]
    r.set_active_time_value(t)
    m = r.read()["internalMesh"]
    b = m.bounds
    sl = m.slice(normal="y", origin=(0, y_m if y_m is not None else 0.5 * (b[2] + b[3]), 0))
    cc = sl.cell_centers().points
    data = {"CO2": np.asarray(sl.cell_data["CO2"]), "T": np.asarray(sl.cell_data["T"]),
            "U": np.linalg.norm(np.asarray(sl.cell_data["U"]), axis=1)}
    return cc, data, t


def _slice_png(cases: dict[str, Path], slug: str, mesh: str):
    style.apply()
    fields = [("CO2", "CO$_2$ (ppm)", "viridis"), ("T", "T (K)", "inferno"), ("U", "|U| (m s$^{-1}$)", "cividis")]
    meta = json.loads((next(iter(cases.values())) / "case_meta.json").read_text())
    sl = {g: _read_slice(c, meta.get("slice_y_m")) for g, c in cases.items()}
    gs = list(cases)
    fig, axes = plt.subplots(len(fields), len(gs), figsize=(3.4 * len(gs), 2.3 * len(fields)), squeeze=False)
    for ri, (f, lab, cmap) in enumerate(fields):
        vmin = min(np.min(sl[g][1][f]) for g in gs)
        vmax = max(np.max(sl[g][1][f]) for g in gs)
        if vmax - vmin < 1e-12:
            vmax = vmin + 1e-12
        for ci, g in enumerate(gs):
            cc, d, t = sl[g]
            ax = axes[ri, ci]
            cs = ax.tricontourf(cc[:, 0] * 1000, cc[:, 2] * 1000, d[f], levels=np.linspace(vmin, vmax, 25), cmap=cmap)
            ax.set_aspect("equal")
            ax.set_title(f"{g}, t = {t:.0f} s: {lab}", fontsize=7.2)
            ax.set_xlabel("x (mm)", fontsize=7)
            ax.set_ylabel("z (mm)", fontsize=7)
            ax.grid(False)
        fig.colorbar(cs, ax=list(axes[ri, :]), shrink=0.85)
    fig.suptitle(f"{slug}: vertical mid-plane, flight (0 g) vs ground control (1 g)", x=0.01, ha="left")
    style.save(fig, f"fields_{slug}_{mesh}")


def run(slug: str, mesh: str = "medium", vtk: bool = False, figs: bool = True) -> dict:
    out = {}
    cases = {}
    for g in ("0g", "1g"):
        c = RUNS / f"{slug}_{g}_{mesh}"
        if not (c / "postProcessing").exists():
            continue
        cases[g] = c
        ts = timeseries(c)
        FIELDS.mkdir(parents=True, exist_ok=True)
        ts.to_csv(FIELDS / f"timeseries_{c.name}.csv", index=False)
        out[g] = metrics(c, ts)
        if vtk:
            to_vtk(c)
    (TABLES / f"M_{slug}_{mesh}.json").write_text(json.dumps(out, indent=1, default=float))
    if figs and cases:
        _slice_png(cases, slug, mesh)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--mesh", default="medium")
    ap.add_argument("--vtk", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(a.slug, a.mesh, a.vtk), indent=1, default=float))
