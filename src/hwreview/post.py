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
    # repeated specimen zones (zone_<name>_ijk) -> equal-volume copies; add their mean as zone_<name>
    if out is not None:
        groups = {}
        for c in out.columns:
            m_ = re.match(r"^(zone_.+)_(\d{3}):(\w+)$", c)
            if m_:
                groups.setdefault((m_.group(1), m_.group(3)), []).append(c)
        for (z, f), cols in groups.items():
            out[f"{z}:{f}"] = out[cols].mean(axis=1)
    return out


def diffusive_patch_flux(case: Path, field: str, D: float, patch_prefix: str = "domain_vent") -> float:
    """Diffusive outflow of `field` through Dirichlet patches at the latest time:
    sum_f D (c_P - c_f) / d_n * A_f  (units field * m3 s-1), with c_P the owner-cell value and
    d_n the owner-centre-to-face distance along the face normal."""
    import pyvista as pv
    from scipy.spatial import cKDTree
    (case / "case.foam").touch()
    r = pv.POpenFOAMReader(str(case / "case.foam"))
    r.set_active_time_value(r.time_values[-1])
    r.enable_all_patch_arrays()
    r.cell_to_point_creation = False
    data = r.read()
    internal = data["internalMesh"]
    cc = internal.cell_centers().points
    tree = cKDTree(cc)
    total = 0.0
    bnd = data["boundary"]
    for name in bnd.keys():
        if not name.startswith(patch_prefix):
            continue
        patch = bnd[name].compute_cell_sizes(length=False, volume=False)
        pn = patch.compute_normals(cell_normals=True, point_normals=False, auto_orient_normals=False)
        fc = patch.cell_centers().points
        area = np.asarray(patch.cell_data["Area"])
        cf = np.asarray(patch.cell_data[field])
        nrm = np.asarray(pn.cell_data["Normals"])
        _, idx = tree.query(fc)
        d = np.abs(np.einsum("ij,ij->i", fc - cc[idx], nrm))
        cp = np.asarray(internal.cell_data[field])[idx]
        total += float(np.sum(D * (cp - cf) / np.maximum(d, 1e-9) * area))
    return total


def metrics(case: Path, ts: pd.DataFrame) -> dict:
    meta = json.loads((case / "case_meta.json").read_text())
    init = meta["initial"]
    T0 = init["T_C"] + 273.15
    res = {"case": case.name, "t_end_s": float(ts.time.max())}
    for col in ts.columns:
        if not col.startswith("zone_") and not col.startswith("domainAvg"):
            continue
        base = {"CO2": init["CO2_ppm"], "H2O": init["H2O_mmol_mol"], "T": T0, "AoA": 0.0}.get(col.split(":")[1])
        if base is None:
            continue
        y = ts[col].values - base
        # plateau mean over the last quarter of the run (same window as the fluctuation estimate)
        final = float(np.mean(y[ts.time >= 0.75 * ts.time.max()]))
        res[f"{col}:final_excess"] = final
        # temporal fluctuation over the last quarter: a 0 g / 1 g difference smaller than this is not resolved
        late = y[ts.time >= 0.75 * ts.time.max()]
        res[f"{col}:late_sd"] = float(np.std(late, ddof=1)) if len(late) > 2 else 0.0
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
    if S_co2 and V and "domainAvg:CO2" in ts and init.get("CO2_ppm") is not None:
        c_air = air["molar_density"]
        S = S_co2 / c_air * 1e6
        late = ts[ts.time >= 0.8 * ts.time.max()]
        t, cavg = late.time.values, late["domainAvg:CO2"].values
        acc = V * np.polyfit(t, cavg, 1)[0] if len(t) > 3 else 0.0
        outflow = 0.0
        if any((case / "constant" / "triSurface").exists() for _ in [0]) and "vent" in (case / "0" / "CO2").read_text():
            outflow += diffusive_patch_flux(case, "CO2", meta["physics"]["D_CO2_m2_s"])
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
    data = {k: np.asarray(sl.cell_data[k]) for k in ("CO2", "T", "AoA") if k in sl.cell_data}
    data["U"] = np.linalg.norm(np.asarray(sl.cell_data["U"]), axis=1)
    return cc, data, t


def _slice_png(cases: dict[str, Path], slug: str, mesh: str):
    style.apply()
    meta = json.loads((next(iter(cases.values())) / "case_meta.json").read_text())
    from . import geometry
    model = geometry.load(slug)
    y_mm = model.spec.get("numerics", {}).get("slice_y_mm")
    sl = {g: _read_slice(c, y_mm / 1000 if y_mm is not None else None) for g, c in cases.items()}
    avail = set.intersection(*[set(v[1]) for v in sl.values()])

    def varies(f):
        lo = min(np.min(sl[g][1][f]) for g in sl)
        hi = max(np.max(sl[g][1][f]) for g in sl)
        return hi - lo > 1e-9 * max(1.0, abs(hi))
    fields = [f for f in [("CO2", "CO$_2$ (ppm)", "viridis"), ("T", "T (K)", "inferno"),
                          ("AoA", "age of air (s)", "magma"), ("U", "|U| (m s$^{-1}$)", "cividis")]
              if f[0] in avail and varies(f[0])]
    import matplotlib.tri as mtri
    obstacles = [o.mesh() for o in model.obstacles]
    tris = {}
    for g, (cc, d, t) in sl.items():
        tr = mtri.Triangulation(cc[:, 0] * 1000, cc[:, 2] * 1000)
        cen = np.column_stack([tr.x[tr.triangles].mean(1), np.full(len(tr.triangles), cc[0, 1] * 1000),
                               tr.y[tr.triangles].mean(1)])
        mask = np.zeros(len(cen), bool)
        for om in obstacles:
            mask |= om.contains(cen)
        # also drop triangles spanning gaps wider than 3 cells (outside the meshed region)
        edge = np.max(np.linalg.norm(np.diff(np.stack([tr.x[tr.triangles], tr.y[tr.triangles]], -1)
                                             [:, [0, 1, 2, 0]], axis=1), axis=-1), axis=1)
        mask |= edge > 3 * meta["cell_mm"]
        tr.set_mask(mask)
        tris[g] = tr
    gs = list(cases)
    fig, axes = plt.subplots(len(fields), len(gs), figsize=(3.4 * len(gs), 2.7 * len(fields)), squeeze=False,
                             gridspec_kw={"hspace": 0.62, "wspace": 0.28})
    for ri, (f, lab, cmap) in enumerate(fields):
        vmin = min(np.min(sl[g][1][f]) for g in gs)
        vmax = max(np.max(sl[g][1][f]) for g in gs)
        for ci, g in enumerate(gs):
            cc, d, t = sl[g]
            ax = axes[ri, ci]
            cs = ax.tricontourf(tris[g], d[f], levels=np.linspace(vmin, vmax, 25), cmap=cmap)
            for om in obstacles:
                sec = om.section(plane_origin=[0, cc[0, 1] * 1000, 0], plane_normal=[0, 1, 0])
                if sec is not None:
                    for ent in sec.entities:
                        pts = sec.vertices[ent.points]
                        ax.fill(pts[:, 0], pts[:, 2], color="#B9BEC6", lw=0)
            ax.set_aspect("equal")
            ax.set_title(f"{g}, t = {t:.0f} s: {lab}", fontsize=7.2)
            ax.set_xlabel("x (mm)", fontsize=7)
            ax.set_ylabel("z (mm)", fontsize=7)
            ax.grid(False)
        fig.colorbar(cs, ax=list(axes[ri, :]), shrink=0.85)
    where = f"vertical plane y = {y_mm:g} mm" if y_mm is not None else "vertical mid-plane"
    what = "flight (0 g) vs ground control (1 g)" if len(gs) == 2 else f"{gs[0]} only (1 g identical by construction)"
    fig.suptitle(f"{slug}: {where}, {what}", x=0.01, ha="left", fontsize=9)
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


FIELD_LABEL = {"CO2": "CO$_2$ (ppm)", "AoA": "age (s)", "T": "T (K)", "H2O": "H$_2$O (mmol/mol)"}


def _tlabel(t: float) -> str:
    return f"{round(t, 3):g}"


def anim_cases(slug: str, mesh: str = "medium") -> dict:
    """Cases the animation is drawn from: the dense-output animation runs (`<case>_anim`, see
    campaign.animation_runs) when every gravity has one, else the production runs."""
    from .campaign import done
    prod = {g: RUNS / f"{slug}_{g}_{mesh}" for g in ("0g", "1g") if (RUNS / f"{slug}_{g}_{mesh}").exists()}
    anim = {g: c.with_name(c.name + "_anim") for g, c in prod.items()}
    if anim and all(c.exists() and done(c) for c in anim.values()):
        return anim
    return prod


def animate(slug: str, mesh: str = "medium", field: str = "CO2", clip_s: float = 6.0):
    """MP4 of the vertical mid-plane over time, 0 g | 1 g side by side (ffmpeg), plus a poster PNG
    of the last frame. Encoded for browsers: H.264 yuv420p, constant 24 fps, moov atom first."""
    import shutil
    import subprocess
    import tempfile

    import matplotlib.tri as mtri
    import pyvista as pv

    from . import geometry
    style.apply()
    cases = anim_cases(slug, mesh)
    readers = {}
    for g, c in cases.items():
        (c / "case.foam").touch()
        readers[g] = pv.POpenFOAMReader(str(c / "case.foam"))
    times = sorted(set.intersection(*[set(r.time_values) for r in readers.values()]))
    model = geometry.load(slug)
    obstacles = [o.mesh() for o in model.obstacles]
    frames, vmin, vmax = [], np.inf, -np.inf
    for t in times:
        fr = {}
        for g, r in readers.items():
            r.set_active_time_value(t)
            m = r.read()["internalMesh"]
            b = m.bounds
            y_mm = model.spec.get("numerics", {}).get("slice_y_mm")
            sl = m.slice(normal="y", origin=(0, y_mm / 1000 if y_mm is not None else 0.5 * (b[2] + b[3]), 0))
            if field not in sl.cell_data:
                return None
            v = np.asarray(sl.cell_data[field])
            v = np.linalg.norm(v, axis=1) if v.ndim == 2 else v
            fr[g] = (sl.cell_centers().points, v)
            vmin, vmax = min(vmin, v.min()), max(vmax, v.max())
        frames.append((t, fr))
    if vmax - vmin <= 1e-9 * max(1.0, abs(vmax)):
        return None                      # uniform field: nothing to animate
    tmp = Path(tempfile.mkdtemp())
    meta = json.loads((next(iter(cases.values())) / "case_meta.json").read_text())
    for k, (t, fr) in enumerate(frames):
        fig, axes = plt.subplots(1, len(fr), figsize=(3.6 * len(fr), 3.0), squeeze=False)
        fig.subplots_adjust(top=0.80)          # room for the figure title above the panel titles
        for ax, (g, (cc, v)) in zip(axes[0], fr.items()):
            tr = mtri.Triangulation(cc[:, 0] * 1000, cc[:, 2] * 1000)
            cen = np.column_stack([tr.x[tr.triangles].mean(1), np.full(len(tr.triangles), cc[0, 1] * 1000),
                                   tr.y[tr.triangles].mean(1)])
            mask = np.zeros(len(cen), bool)
            for om in obstacles:
                mask |= om.contains(cen)
            edge = np.max(np.linalg.norm(np.diff(np.stack([tr.x[tr.triangles], tr.y[tr.triangles]], -1)
                                                 [:, [0, 1, 2, 0]], axis=1), axis=-1), axis=1)
            tr.set_mask(mask | (edge > 3 * meta["cell_mm"]))
            cs = ax.tricontourf(tr, v, levels=np.linspace(vmin, vmax, 25), cmap="viridis")
            ax.set_aspect("equal")
            ax.set_title(f"{g}   t = {_tlabel(t)} s", fontsize=8)
            ax.set_xlabel("x (mm)", fontsize=7)
            ax.set_ylabel("z (mm)", fontsize=7)
            ax.grid(False)
        fig.colorbar(cs, ax=list(axes[0]), shrink=0.85, label=FIELD_LABEL.get(field, field))
        fig.suptitle(f"{slug}: {field}, vertical mid-plane", x=0.01, ha="left", fontsize=9)
        fig.savefig(tmp / f"f{k:04d}.png", dpi=110)
        plt.close(fig)
    out = FIGURES / f"anim_{slug}_{mesh}_{field}.mp4"
    fps = max(4, round(len(frames) / clip_s))          # whole run in about clip_s seconds
    vf = ("pad=ceil(iw/2)*2:ceil(ih/2)*2,tpad=stop_mode=clone:stop_duration=1.5,"   # hold the end state
          "fps=24,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "f%04d.png"),
                    "-vf", vf, "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "20",
                    "-movflags", "+faststart", "-an", str(out)], check=True)
    shutil.copy2(tmp / f"f{len(frames) - 1:04d}.png", FIGURES / f"anim_{slug}_{mesh}_{field}_poster.png")
    shutil.rmtree(tmp)
    return out


def animation_consistency(slugs, mesh: str = "medium"):
    """Animation run vs production run (same mesh and settings; only end time and write interval
    differ). Compares the specimen-zone mean over the last third of the animation window; for unsteady
    flows the instantaneous states diverge, so the production run's s.d. over the same window is given
    for scale. Quantities whose excess is only round-off are skipped. Writes T10_animation_consistency.csv."""
    rows = []
    for slug in slugs:
        for g, ca in anim_cases(slug, mesh).items():
            if not ca.name.endswith("_anim"):
                continue
            cp = ca.with_name(ca.name[:-len("_anim")])
            ta, tp = timeseries(ca), timeseries(cp)
            meta = json.loads((cp / "case_meta.json").read_text())
            t_end = float(ta.time.max())
            w0 = 2 / 3 * t_end
            wa, wp = ta[ta.time >= w0], tp[(tp.time >= w0) & (tp.time <= t_end)]
            # specimen zones (aggregate only, not the per-vial copies); the whole domain when there is no zone
            cols = [c for c in ta.columns if c.startswith("zone_") and not re.search(r"_\d{3}:", c)] \
                or [c for c in ta.columns if c.startswith("domainAvg:")]
            for col in [c for c in cols if c.split(":")[1] in ("CO2", "T", "AoA")]:
                if col not in tp:
                    continue
                q = col.split(":")[1]
                ref = {"CO2": meta["initial"]["CO2_ppm"], "T": meta["initial"]["T_C"] + 273.15, "AoA": 0.0}[q]
                # compare at the sparser run's sample times, interpolating the denser one
                if 0 < len(wp) < len(wa):
                    a = float(np.mean(np.interp(wp.time, ta.time, ta[col])))
                    b = float(wp[col].mean())
                else:
                    a = float(wa[col].mean())
                    b = float(np.mean(np.interp(wa.time, tp.time, tp[col])))
                exc = b - ref
                if abs(exc) < (1e-3 if q == "T" else 1e-6):
                    continue                  # no source for this quantity: excess is round-off
                rows.append({"model": slug, "gravity": g, "window_start_s": w0, "window_end_s": t_end,
                             "quantity": col, "animation_run_mean": a, "production_run_mean": b,
                             "abs_diff": abs(a - b), "rel_diff_of_excess_pct": 100 * abs(a - b) / abs(exc),
                             "production_window_sd": float(wp[col].std(ddof=1)) if len(wp) > 1 else float("nan")})
    df = pd.DataFrame(rows)
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / "T10_animation_consistency.csv", index=False)
    return df
