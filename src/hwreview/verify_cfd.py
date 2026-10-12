"""CFD verification against benchmarks with published reference values.

V1  Differentially heated square cavity (air, Pr = 0.71), Ra = 1e4, 1e5, 1e6.
    Reference mean hot-wall Nusselt numbers, as tabulated in Table 1 of
    Gjesdal, Wasberg & Andreassen (2003) arXiv:physics/0305049:
      de Vahl Davis (1983) Int. J. Numer. Meth. Fluids 3:249-264 : 2.243, 4.519, 8.800
      Hortmann, Peric & Scheurer (1990)                           : 2.245, 4.522, 8.825
    Solved with the same solver, schemes and Boussinesq settings used for the
    hardware cases (buoyantBoussinesqPimpleFoam, OpenFOAM v2606), run to steady state.

V2  Pure diffusion of a passive scalar (the CO2/H2O transport used in the hardware
    cases): 1-D slab with fixed values at both ends from a uniform start, compared
    with the analytic Fourier-series solution at several times.

    python -m hwreview.verify_cfd [--n 64 96 128]
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np

from . import foam
from .foam import Raw, write, write_field
from .paths import RUNS, TABLES

REF_NU = {1e4: (2.243, 2.245), 1e5: (4.519, 4.522), 1e6: (8.800, 8.825)}
REF_SOURCE = ("Gjesdal T., Wasberg C.E., Andreassen O. (2003) Spectral element simulations of "
              "buoyancy-driven flow. arXiv:physics/0305049, Table 1")
PR = 0.71
END = {1e4: 300, 1e5: 300, 1e6: 600}


def _common(case, nu, kappa_over_nu_Pr, end_time, write_interval, max_co=0.7, dt=1e-3):
    write(case / "system" / "controlDict", "dictionary", "controlDict", {
        "application": "buoyantBoussinesqPimpleFoam", "startFrom": "latestTime", "startTime": 0,
        "stopAt": "endTime", "endTime": end_time, "deltaT": dt, "writeControl": "adjustableRunTime",
        "writeInterval": write_interval, "purgeWrite": 0, "writeFormat": "ascii", "writePrecision": 10,
        "writeCompression": "off", "timeFormat": "general", "timePrecision": 8, "runTimeModifiable": "true",
        "adjustTimeStep": "yes", "maxCo": max_co, "maxDeltaT": 1.0,
    })
    write(case / "system" / "fvSchemes", "dictionary", "fvSchemes", {
        "ddtSchemes": {"default": "backward"},
        "gradSchemes": {"default": "Gauss linear"},
        "divSchemes": {"default": "none", "div(phi,U)": "Gauss linear", "div(phi,T)": "Gauss linear",
                       "div((nuEff*dev2(T(grad(U)))))": "Gauss linear"},
        "laplacianSchemes": {"default": "Gauss linear corrected"},
        "interpolationSchemes": {"default": "linear"},
        "snGradSchemes": {"default": "corrected"},
    })
    write(case / "system" / "fvSolution", "dictionary", "fvSolution", {
        "solvers": {
            "p_rgh": {"solver": "PCG", "preconditioner": "DIC", "tolerance": 1e-9, "relTol": 0.01},
            "p_rghFinal": {"$p_rgh": "", "relTol": 0},
            "\"(U|T)\"": {"solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-10, "relTol": 0},
            "\"(U|T)Final\"": {"solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-10, "relTol": 0},
        },
        "PIMPLE": {"momentumPredictor": "yes", "nOuterCorrectors": 1, "nCorrectors": 2,
                   "nNonOrthogonalCorrectors": 0, "pRefCell": 0, "pRefValue": 0},
    })
    write(case / "constant" / "transportProperties", "dictionary", "transportProperties", {
        "transportModel": "Newtonian", "nu": nu, "beta": 1.0, "TRef": 0.5, "Pr": PR, "Prt": 0.85})
    write(case / "constant" / "turbulenceProperties", "dictionary", "turbulenceProperties",
          {"simulationType": "laminar"})


def cavity_case(ra: float, n: int, grading: float = 4.0):
    """Unit square, hot left wall T=1, cold right wall T=0, adiabatic top/bottom, g=(0,-1,0)."""
    case = RUNS / f"verify_dvd2_Ra{ra:.0e}_n{n}"
    nu = math.sqrt(PR / ra)          # g = beta = dT = L = 1  ->  Ra = 1/(nu*kappa), Pr = nu/kappa
    # symmetric wall grading: first/last cell 1/grading of the centre cell
    write(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict", f"""
convertToMeters 1;
vertices ( (0 0 0) (1 0 0) (1 1 0) (0 1 0) (0 0 0.01) (1 0 0.01) (1 1 0.01) (0 1 0.01) );
blocks ( hex (0 1 2 3 4 5 6 7) ({n} {n} 1)
         simpleGrading ( ((0.5 0.5 {grading}) (0.5 0.5 {1/grading})) ((0.5 0.5 {grading}) (0.5 0.5 {1/grading})) 1 ) );
boundary
(
    hot  {{ type wall; faces ((0 4 7 3)); }}
    cold {{ type wall; faces ((1 2 6 5)); }}
    adiabatic {{ type wall; faces ((0 1 5 4) (3 7 6 2)); }}
    frontAndBack {{ type empty; faces ((0 3 2 1) (4 5 6 7)); }}
);
""")
    write(case / "constant" / "g", "uniformDimensionedVectorField", "g",
          "dimensions [0 1 -2 0 0 0 0];\nvalue (0 -1 0);\n")
    _common(case, nu, None, end_time=END[ra], write_interval=10)
    walls = {"hot": None, "cold": None, "adiabatic": None, "frontAndBack": {"type": "empty"}}
    write_field(case, "U", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
                {k: (v or {"type": "noSlip"}) for k, v in walls.items()}, cls="volVectorField")
    write_field(case, "T", "[0 0 0 1 0 0 0]", "uniform 0.5",
                {"hot": {"type": "fixedValue", "value": "uniform 1"},
                 "cold": {"type": "fixedValue", "value": "uniform 0"},
                 "adiabatic": {"type": "zeroGradient"}, "frontAndBack": {"type": "empty"}})
    for f, dims in (("p_rgh", "[0 2 -2 0 0 0 0]"), ("p", "[0 2 -2 0 0 0 0]")):
        write_field(case, f, dims, "uniform 0",
                    {k: ({"type": "fixedFluxPressure", "value": "uniform 0"} if f == "p_rgh" else
                         {"type": "calculated", "value": "uniform 0"}) if v is None else v
                     for k, v in walls.items()})
    write_field(case, "alphat", "[0 2 -1 0 0 0 0]", "uniform 0",
                {k: ({"type": "calculated", "value": "uniform 0"} if v is None else v) for k, v in walls.items()})
    return case


def nusselt(case, n, t):
    """Mean wall Nusselt numbers (hot, cold) of the field at time t.

    dT/dx at each wall from a second-order one-sided fit through the wall value and
    the two nearest cell centres in each row, integrated over the wall height.
    """
    T = foam.read_internal(case / t / "T").reshape(n, n)       # blockMesh order: x fastest
    C = foam.read_internal(case / foam.time_dirs(case)[-1] / "C")
    x = C[:, 0].reshape(n, n)
    y = C[:, 1].reshape(n, n)[:, 0]
    edges = np.diff(np.concatenate([[0], 0.5 * (y[1:] + y[:-1]), [1]]))

    def grad(d1, d2, t1, t2, tw):
        a = ((t1 - tw) / d1 - (t2 - tw) / d2) / (d1 - d2)
        return (t1 - tw) / d1 - a * d1
    hot = -grad(x[:, 0], x[:, 1], T[:, 0], T[:, 1], 1.0)
    cold = grad(1 - x[:, -1], 1 - x[:, -2], T[:, -1], T[:, -2], 0.0)
    return float(np.sum(hot * edges)), float(np.sum(cold * edges))


def nusselt_window(case, n, end):
    """Hot/cold mean Nu averaged over all outputs in the last third of the run."""
    ts = [t for t in foam.time_dirs(case) if float(t) >= 2 * end / 3 - 1e-9]
    vals = np.array([nusselt(case, n, t) for t in ts])
    both = vals.mean(axis=1)
    return {"Nu": float(both.mean()), "Nu_time_sd": float(both.std(ddof=1)) if len(both) > 1 else 0.0,
            "Nu_hot": float(vals[:, 0].mean()), "Nu_cold": float(vals[:, 1].mean()), "n_outputs": len(ts)}


def run_cavity(ns=(64, 96, 128), ras=None):
    rows = []
    for ra in (ras or REF_NU):
        for n in ns:
            case = cavity_case(ra, n)
            if not (case / "constant" / "polyMesh" / "points").exists():
                foam.run(case, ["blockMesh"])
            last = foam.time_dirs(case)
            if not last or float(last[-1]) < END[ra] - 1e-9:
                foam.run(case, ["buoyantBoussinesqPimpleFoam"])
            foam.run(case, ["postProcess -func writeCellCentres -latestTime"])
            r = nusselt_window(case, n, END[ra])
            dvd, hort = REF_NU[ra]
            rows.append({"Ra": ra, "n": n, **{k: round(v, 5) for k, v in r.items()}, "t_end": END[ra],
                         "ref_deVahlDavis": dvd, "ref_Hortmann": hort,
                         "err_vs_Hortmann_pct": round(100 * (r["Nu"] - hort) / hort, 3)})
            print(rows[-1], flush=True)
    return rows


def diffusion_case(n=200, D=1.6e-5, L=0.05):
    """1-D slab, c=1 at x=0 and x=L, c=0 initially; scalarTransport with phi = 0."""
    case = RUNS / f"verify_diffusion_n{n}"
    write(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict", f"""
convertToMeters 1;
vertices ( (0 0 0) ({L} 0 0) ({L} 0.001 0) (0 0.001 0) (0 0 0.001) ({L} 0 0.001) ({L} 0.001 0.001) (0 0.001 0.001) );
blocks ( hex (0 1 2 3 4 5 6 7) ({n} 1 1) simpleGrading (1 1 1) );
boundary
(
    left  {{ type patch; faces ((0 4 7 3)); }}
    right {{ type patch; faces ((1 2 6 5)); }}
    sides {{ type empty; faces ((0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7)); }}
);
""")
    t_end = 0.1 * L ** 2 / D
    write(case / "system" / "controlDict", "dictionary", "controlDict", {
        "application": "scalarTransportFoam", "startFrom": "startTime", "startTime": 0, "stopAt": "endTime",
        "endTime": round(t_end, 6), "deltaT": round(t_end / 2000, 8), "writeControl": "runTime",
        "writeInterval": round(t_end / 4, 6), "writeFormat": "ascii", "writePrecision": 12,
        "timeFormat": "general", "timePrecision": 10})
    write(case / "system" / "fvSchemes", "dictionary", "fvSchemes", {
        "ddtSchemes": {"default": "CrankNicolson 0.9"}, "gradSchemes": {"default": "Gauss linear"},
        "divSchemes": {"default": "none", "div(phi,T)": "Gauss linear"},
        "laplacianSchemes": {"default": "Gauss linear corrected"},
        "interpolationSchemes": {"default": "linear"}, "snGradSchemes": {"default": "corrected"}})
    write(case / "system" / "fvSolution", "dictionary", "fvSolution", {
        "solvers": {"T": {"solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-12, "relTol": 0}},
        "SIMPLE": {"nNonOrthogonalCorrectors": 0}})
    write(case / "constant" / "transportProperties", "dictionary", "transportProperties", {"DT": D})
    write_field(case, "T", "[0 0 0 0 0 0 0]", "uniform 0",
                {"left": {"type": "fixedValue", "value": "uniform 1"},
                 "right": {"type": "fixedValue", "value": "uniform 1"}, "sides": {"type": "empty"}})
    write_field(case, "U", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
                {"left": {"type": "fixedValue", "value": "uniform (0 0 0)"},
                 "right": {"type": "fixedValue", "value": "uniform (0 0 0)"}, "sides": {"type": "empty"}},
                cls="volVectorField")
    return case, D, L


def analytic_slab(x, t, D, L, terms=400):
    s = np.zeros_like(x)
    for k in range(terms):
        m = 2 * k + 1
        s += (4 / (m * math.pi)) * np.sin(m * math.pi * x / L) * math.exp(-(m * math.pi / L) ** 2 * D * t)
    return 1 - s


def run_diffusion():
    case, D, L = diffusion_case()
    if not (case / "constant" / "polyMesh" / "points").exists() or len(foam.time_dirs(case)) < 2:
        foam.run(case, ["blockMesh", "scalarTransportFoam", "postProcess -func writeCellCentres"])
    rows = []
    for t in foam.time_dirs(case)[1:]:
        c = foam.read_internal(case / t / "T")
        x = foam.read_internal(case / "0" / "C")[:, 0] if (case / "0" / "C").exists() else \
            foam.read_internal(case / t / "C")[:, 0]
        a = analytic_slab(x, float(t), D, L)
        rows.append({"t_s": float(t), "Fo": float(t) * D / L ** 2,
                     "max_abs_err": float(np.max(np.abs(c - a))), "rms_err": float(np.sqrt(np.mean((c - a) ** 2)))})
        print(rows[-1], flush=True)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[64, 96, 128])
    ap.add_argument("--only", choices=["cavity", "diffusion"])
    ap.add_argument("--ra", type=float, nargs="+")
    a = ap.parse_args()
    out = {}
    if a.only in (None, "diffusion"):
        out["diffusion"] = run_diffusion()
    if a.only in (None, "cavity"):
        out["cavity"] = run_cavity(tuple(a.n), a.ra)
        out["reference_source"] = REF_SOURCE
    TABLES.mkdir(parents=True, exist_ok=True)
    tag = ("_" + a.only if a.only else "") + ("_Ra" + "_".join(f"{r:.0e}" for r in a.ra) if a.ra else "")
    (TABLES / f"V_verification{tag}.json").write_text(json.dumps(out, indent=1))
