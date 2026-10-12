"""Grid convergence index (Celik et al. 2008, J. Fluids Eng. 130:078001) for the mesh ladders.

For three meshes (fine 1, medium 2, coarse 3) with representative cell size
h = (V / N)^(1/3) and solutions phi1..phi3:
    r21 = h2/h1, r32 = h3/h2, e21 = phi2 - phi1, e32 = phi3 - phi2, s = sign(e32/e21)
    p   = |ln|e32/e21| + q(p)| / ln r21,   q(p) = ln((r21^p - s)/(r32^p - s))   (fixed-point)
    phi_ext = (r21^p phi1 - phi2)/(r21^p - 1)
    GCI_fine = 1.25 |(phi1 - phi2)/phi1| / (r21^p - 1)
Oscillatory convergence (e32/e21 < 0) is flagged; p is then not meaningful and the
GCI is reported with that caveat. Writes results/tables/T7_gci.csv.
"""
from __future__ import annotations

import json
import math
import re

import numpy as np
import pandas as pd

from . import post
from .paths import RUNS, TABLES

QUANTITIES = ["zone_{z}:CO2:final_excess", "zone_{z}:T:final_excess", "zone_{z}:AoA:final_excess",
              "domainAvg:CO2:final_excess", "domainAvg:AoA:final_excess", "U_max_late_m_s"]


def h_of(case) -> tuple[float, int]:
    log = (case / "log.checkMesh").read_text()
    n = int(re.search(r"cells:\s+(\d+)", log).group(1))
    v = float(re.search(r"Total volume = ([0-9.eE+-]+)", log).group(1).rstrip("."))
    return (v / n) ** (1 / 3), n


def gci3(phi, h):
    """phi, h ordered fine, medium, coarse."""
    p1, p2, p3 = phi
    h1, h2, h3 = h
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = p2 - p1, p3 - p2
    out = {"phi_fine": p1, "phi_medium": p2, "phi_coarse": p3, "r21": r21, "r32": r32}
    if abs(e21) < 1e-14 * max(1, abs(p1)) or abs(e32) < 1e-14 * max(1, abs(p1)):
        out.update({"p": float("nan"), "phi_ext": p1, "gci_fine_pct": 0.0, "convergence": "converged to round-off"})
        return out
    ratio = e32 / e21
    s = math.copysign(1, ratio)
    p = 2.0
    for _ in range(200):
        q = math.log((r21 ** p - s) / (r32 ** p - s)) if (r21 ** p - s) > 0 and (r32 ** p - s) > 0 else 0.0
        p_new = abs(math.log(abs(ratio)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-10:
            break
        p = p_new
    phi_ext = (r21 ** p * p1 - p2) / (r21 ** p - 1)
    ea = abs((p1 - p2) / p1) if p1 else float("nan")
    out.update({"p": p, "phi_ext": phi_ext, "e_a21_pct": 100 * ea,
                "e_ext21_pct": 100 * abs((phi_ext - p1) / phi_ext) if phi_ext else float("nan"),
                "gci_fine_pct": 100 * 1.25 * ea / (r21 ** p - 1),
                "convergence": "oscillatory" if ratio < 0 else "monotonic"})
    return out


def run():
    rows = []
    for slug in ("mds", "aph", "vented_fly_box_vent20"):
        for g in ("0g", "1g"):
            cs = [RUNS / f"{slug}_{g}_{m}" for m in ("fine", "medium", "coarse")]
            from .campaign import done
            if not all(c.exists() and done(c) for c in cs):
                continue                      # only complete runs enter the GCI
            mets = [post.metrics(c, post.timeseries(c)) for c in cs]
            hs = [h_of(c) for c in cs]
            zone = json.loads((cs[0] / "case_meta.json").read_text())["sources_total"]
            zname = next(iter(zone)) if zone else None
            for qt in QUANTITIES:
                key = qt.format(z=zname) if zname else qt
                if not all(key in m and m[key] is not None for m in mets):
                    continue
                # quantities that are zero up to round-off (e.g. T excess with no heat source) have no GCI
                if max(abs(m[key]) for m in mets) < (1e-3 if ":T:" in key else 1e-9):
                    continue
                r = gci3([m[key] for m in mets], [h[0] for h in hs])
                sd = mets[0].get(key.replace(":final_excess", ":late_sd")) if key.endswith(":final_excess") else None
                spread = max(m[key] for m in mets) - min(m[key] for m in mets)
                rows.append({"model": slug, "gravity": g, "quantity": key,
                             "N_fine": hs[0][1], "N_medium": hs[1][1], "N_coarse": hs[2][1], **r,
                             "temporal_sd_fine": sd,
                             # mesh-to-mesh spread smaller than ~2 temporal sd: not separable from unsteadiness
                             "mesh_spread_within_unsteadiness": bool(sd and spread < 2 * sd)})
    df = pd.DataFrame(rows)
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / "T7_gci.csv", index=False)
    return df


if __name__ == "__main__":
    d = run()
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(d[["model", "gravity", "quantity", "phi_fine", "phi_medium", "phi_coarse", "p", "gci_fine_pct",
                 "convergence"]].to_string(index=False))
