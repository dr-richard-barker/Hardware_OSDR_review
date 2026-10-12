"""Run the CFD campaign: every Tier-A model in 0 g and 1 g, with mesh ladders for the GCI study.

    python -m hwreview.campaign [--np 12] [--only aph,mds]

Resumable: a case whose solver log reached its end time is skipped. Progress is
appended to runs/campaign.log; failures are logged and the queue continues.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import traceback

from . import cases, foam, geometry
from .paths import RUNS

# (model, meshes, gravities). Hardware with no sourced heat load has no buoyancy source in the
# Boussinesq model, so its 1 g solution is identical to 0 g by construction; running it only adds
# round-off-driven spurious currents (seen in a trial 1 g run of the passive fly box), so such models run 0 g only.
# APH keeps both gravities as a demonstration that the 0 g / 1 g difference is within the temporal
# fluctuation of the forced flow.
CAMPAIGN = [
    ("mds", ["coarse", "medium", "fine"], ["0g", "1g"]),
    ("aph", ["coarse", "medium", "fine"], ["0g", "1g"]),
    ("vented_fly_box_vent20", ["coarse", "medium", "fine"], ["0g"]),
    ("vented_fly_box_vent60", ["medium"], ["0g"]),
    ("aph_fanmax", ["medium"], ["0g"]),
    ("aqh", ["medium"], ["0g"]),
]


def done(case) -> bool:
    log = case / "log.reconstructPar_-newTimes"
    if not log.exists():
        return False
    end = float(json.loads((case / "case_meta.json").read_text())["numerics"]["end_time_s"])
    times = [float(t) for t in foam.time_dirs(case)]
    return bool(times) and max(times) >= end - 1e-6


TAG = ""


def log(msg: str):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {TAG}{msg}"
    print(line, flush=True)
    with open(RUNS / "campaign.log", "a") as f:
        f.write(line + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--np", type=int, default=12)
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    global TAG
    TAG = f"[np{a.np}] " if a.only else ""
    only = set(a.only.split(",")) if a.only else None
    for slug, meshes, gravities in CAMPAIGN:
        if only and slug not in only:
            continue
        for mesh in meshes:
            for g in gravities:
                case = RUNS / f"{slug}_{g}_{mesh}"
                try:
                    if case.exists() and done(case):
                        log(f"skip  {case.name} (complete)")
                        continue
                    t0 = dt.datetime.now()
                    case = cases.build(slug, g, mesh, a.np)
                    if not (case / "constant" / "polyMesh" / "cellZones").exists():
                        cases.mesh_case(case, a.np)
                    ncell = re.search(r"cells:\s+(\d+)", (case / "log.checkMesh").read_text()).group(1)
                    log(f"start {case.name} cells={ncell}")
                    cases.solve(case, a.np)
                    log(f"done  {case.name} in {(dt.datetime.now() - t0).total_seconds():.0f} s")
                except Exception as e:  # keep the queue moving; the failure is recorded
                    log(f"FAIL  {case.name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
                    (RUNS / f"{case.name}.error.txt").write_text(traceback.format_exc())


if __name__ == "__main__":
    main()
