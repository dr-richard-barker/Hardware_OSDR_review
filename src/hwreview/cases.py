"""Stage 6 - build and run a 3-D transient OpenFOAM case for one hardware model.

    python -m hwreview.cases <slug> --gravity 0g|1g --mesh coarse|medium|fine [--run] [--np 8]

Physics (laminar, Boussinesq air, buoyantBoussinesqPimpleFoam, OpenFOAM v2606):
  * momentum + energy, gravity (0, 0, -9.81) m s-2 for 1 g or zero for 0 g;
  * CO2 [ppm] and H2O [mmol mol-1] as passive scalars (scalarTransport function
    objects) with molecular diffusivities from physics.py;
  * specimen zones (cellZones) carry volumetric sources: CO2, H2O and heat, converted
    from the sourced fluxes in the hardware file (units handled in to_mol_s/to_W);
  * walls: no-slip, fixed temperature (hardware set-point), impermeable to gases;
  * inlet: flowRateInletVelocity at the sourced volumetric flow, supply T/CO2/H2O;
  * outlet: fixed p_rgh, inletOutlet scalars;
  * membranes: no-slip, Robin (mixed) condition for gases with the sourced permeance.

Numerical settings (mesh size, write interval, end time) live in the model's
`numerics:` block; they are verified by the GCI study rather than sourced.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from . import foam, geometry, physics
from .foam import write, write_field
from .paths import RUNS

MESH_FACTOR = {"coarse": 1.0, "medium": 1 / 1.41421356, "fine": 0.5}   # refinement ratio sqrt(2)


# ----------------------------------------------------------------------------- units
def to_mol_s(rate: float, unit: str, area_m2: float | None = None, count: float = 1.0) -> float:
    """Convert a gas flux to mol s-1 for the whole zone."""
    u = unit.replace(" ", "").replace("^", "").replace("−", "-")
    per_area = {"umolm-2s-1": 1e-6, "µmolm-2s-1": 1e-6, "mmolm-2s-1": 1e-3, "molm-2s-1": 1.0}
    per_item = {"mol/s": 1.0, "umol/s": 1e-6, "µmol/s": 1e-6, "mmol/s": 1e-3, "mmol/h": 1e-3 / 3600,
                "umol/h": 1e-6 / 3600, "mol/h": 1 / 3600, "mol/day": 1 / 86400, "mmol/day": 1e-3 / 86400,
                "mL/min": 1 / 22414.0 / 60, "ml/min": 1 / 22414.0 / 60, "L/h": 1 / 22.414 / 3600,
                "mL/h": 1 / 22414.0 / 3600, "ml/h": 1 / 22414.0 / 3600, "L/day": 1 / 22.414 / 86400,
                "g/h": None, "g/day": None, "mg/h": None, "nmol/s": 1e-9}
    if u in per_area:
        if area_m2 is None:
            raise ValueError(f"{unit} needs area_m2")
        return rate * per_area[u] * area_m2 * count
    if u in per_item and per_item[u] is not None:
        return rate * per_item[u] * count
    raise ValueError(f"unsupported gas-flux unit {unit!r} (mass units need the species: use to_mol_s_mass)")


def to_mol_s_mass(rate: float, unit: str, molar_mass: float, count: float = 1.0) -> float:
    g_s = {"g/h": 1 / 3600, "g/day": 1 / 86400, "mg/h": 1e-3 / 3600, "g/s": 1.0, "mg/s": 1e-3}[unit.replace(" ", "")]
    return rate * g_s / molar_mass * count


def to_W(rate: float, unit: str, count: float = 1.0) -> float:
    f = {"W": 1.0, "mW": 1e-3, "kcal/day": 4184 / 86400, "kcal/h": 4184 / 3600, "kJ/day": 1000 / 86400,
         "J/s": 1.0}[unit.replace(" ", "")]
    return rate * f * count


MOLAR_MASS = {"CO2": 44.0095, "H2O": 18.01528}   # g mol-1, IUPAC standard atomic weights


# ----------------------------------------------------------------------------- helpers
def _mid(v):
    return float(np.mean(v)) if isinstance(v, (list, tuple)) else float(v)


def _env(m: geometry.Model, key: str, R) -> float:
    e = m.spec.get("environment", {})
    return _mid(R(e[key], f"environment.{key}"))


def zone_sources(m: geometry.Model, R) -> dict:
    """Total sources per spec zone: {zone: {'total': {CO2_mol_s, H2O_mol_s, heat_W}, 'copies': n}}.

    A zone with `repeat` is meshed as one cellZone per copy; the total is split evenly.
    Uptake (e.g. photosynthetic CO2 fixation) is written with `uptake: true`.
    """
    out = {}
    for z in m.spec.get("zones") or []:
        n_rep = int(np.prod(z.get("repeat", {}).get("n", [1, 1, 1])))
        tot = {"CO2_mol_s": 0.0, "H2O_mol_s": 0.0, "heat_W": 0.0}
        for sp, d in (z.get("sources") or {}).items():
            w = f"zones.{z['name']}.sources.{sp}"
            rate = _mid(R(d["rate"], f"{w}.rate"))
            count = _mid(R(d["count"], f"{w}.count")) if "count" in d else 1.0
            area = _mid(R(d["area_m2"], f"{w}.area_m2")) if "area_m2" in d else None
            sign = -1.0 if d.get("uptake") else 1.0
            if sp == "heat":
                tot["heat_W"] += sign * to_W(rate, d["unit"], count)
            elif d["unit"].replace(" ", "") in ("g/h", "g/day", "mg/h", "g/s", "mg/s"):
                tot[f"{sp}_mol_s"] += sign * to_mol_s_mass(rate, d["unit"], MOLAR_MASS[sp], count)
            else:
                tot[f"{sp}_mol_s"] += sign * to_mol_s(rate, d["unit"], area, count)
        out[z["name"]] = {"total": tot, "copies": n_rep}
    return out


# ----------------------------------------------------------------------------- case writer
def build(slug: str, gravity: str = "0g", mesh: str = "medium", nprocs: int = 8, tag: str = "") -> Path:
    m = geometry.load(slug)
    errs = geometry.validate(m)
    if errs:
        raise ValueError(f"{slug}: geometry invalid:\n  " + "\n  ".join(errs))
    R = geometry.Resolver(m.hw, m.spec.get("assumptions") or [])
    num = m.spec["numerics"]
    case = RUNS / f"{slug}_{gravity}_{mesh}{tag}"
    tri = case / "constant" / "triSurface"
    info = geometry.write_stl(m, tri)

    T_c = _env(m, "temperature_C", R)
    p_kpa = _env(m, "pressure_kPa", R) if "pressure_kPa" in m.spec.get("environment", {}) else 101.325
    props = physics.provenance(T_c, p_kpa)
    air = props["air"]
    D_CO2, D_H2O = props["D_CO2_m2_s"], props["D_H2O_m2_s"]
    co2_0 = _env(m, "co2_ppm", R)
    h2o_0 = _env(m, "h2o_mmol_mol", R) if "h2o_mmol_mol" in m.spec.get("environment", {}) else None
    if h2o_0 is None:
        rh = _env(m, "rh_percent", R)
        es = physics.p_sat_water_kpa(T_c)                       # IAPWS via CoolProp
        h2o_0 = rh / 100 * es / p_kpa * 1000                   # mmol mol-1
    c_air = air["molar_density"]

    # --- blockMesh background: domain bounding box, cubic cells
    lo, hi = m.domain.bounds()
    h = float(num["cell_mm"]) * MESH_FACTOR[mesh]
    margin = h
    blo, bhi = (lo - margin) / 1000, (hi + margin) / 1000
    n = np.maximum(1, np.round((bhi - blo) * 1000 / h)).astype(int)
    v = [(blo[0], blo[1], blo[2]), (bhi[0], blo[1], blo[2]), (bhi[0], bhi[1], blo[2]), (blo[0], bhi[1], blo[2]),
         (blo[0], blo[1], bhi[2]), (bhi[0], blo[1], bhi[2]), (bhi[0], bhi[1], bhi[2]), (blo[0], bhi[1], bhi[2])]
    write(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict",
          "convertToMeters 1;\nvertices (\n" + "\n".join(f"    ({a:.9g} {b:.9g} {c:.9g})" for a, b, c in v)
          + f"\n);\nblocks ( hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1) );\n"
          "boundary ( background { type patch; faces ((0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7)); } );\n")

    # --- snappyHexMesh
    roles = info["patch_roles"]
    regions = "\n".join(
        f"                {r} {{ level ({num.get('surface_level', 0)} {num.get('surface_level', 0)}); "
        f"patchInfo {{ type {'wall' if role in ('wall', 'membrane') else 'patch'}; }} }}" for r, role in roles.items())
    has_obs = bool(m.obstacles)
    obs_geom = "    obstacles.stl { type triSurfaceMesh; name obstacles; }\n" if has_obs else ""
    obs_ref = (f"        obstacles {{ level ({num.get('obstacle_level', 1)} {num.get('obstacle_level', 1)}); "
               "patchInfo { type wall; } }\n") if has_obs else ""
    feats = '        { file "domain.eMesh"; level %d; }\n' % num.get("surface_level", 0)
    if has_obs:
        feats += '        { file "obstacles.eMesh"; level %d; }\n' % num.get("obstacle_level", 1)
    loc = geometry.inside_point(m)
    write(case / "system" / "snappyHexMeshDict", "dictionary", "snappyHexMeshDict", f"""
castellatedMesh true;
snap            true;
addLayers       false;
geometry
{{
    domain.stl {{ type triSurfaceMesh; name domain; }}
{obs_geom}}};
castellatedMeshControls
{{
    maxLocalCells 2000000; maxGlobalCells 8000000; minRefinementCells 0; maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3;
    features
    (
{feats}    );
    refinementSurfaces
    {{
        domain
        {{
            level ({num.get('surface_level', 0)} {num.get('surface_level', 0)});
            regions
            {{
{regions}
            }}
        }}
{obs_ref}    }}
    resolveFeatureAngle 30;
    refinementRegions {{ }}
    locationInMesh ({loc[0]:.9g} {loc[1]:.9g} {loc[2]:.9g});
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 3; tolerance 2.0; nSolveIter 50; nRelaxIter 5;
    nFeatureSnapIter 10; implicitFeatureSnap false; explicitFeatureSnap true; multiRegionFeatureSnap true;
}}
addLayersControls
{{
    relativeSizes true; layers {{ }} expansionRatio 1.2; finalLayerThickness 0.3; minThickness 0.1;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-16;
    minTetQuality 1e-15; minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.05;
    minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
    relaxed {{ maxNonOrtho 75; }}
}}
mergeTolerance 1e-6;
""")
    write(case / "system" / "surfaceFeatureExtractDict", "dictionary", "surfaceFeatureExtractDict",
          "".join(f"{s}\n{{\n    extractionMethod extractFromSurface;\n    includedAngle 150;\n"
                  "    subsetFeatures { nonManifoldEdges no; openEdges yes; }\n    writeObj no;\n}\n"
                  for s in (["domain.stl"] + (["obstacles.stl"] if has_obs else []))))

    # --- topoSet: one cellZone per specimen zone (repeats -> one zone each)
    actions = []
    zone_names = []
    for z in m.zones:
        b = z.bounds() / 1000
        nm = z.name
        zone_names.append(nm)
        if z.shape == "box":
            src = f"source boxToCell; box ({b[0][0]:.9g} {b[0][1]:.9g} {b[0][2]:.9g}) ({b[1][0]:.9g} {b[1][1]:.9g} {b[1][2]:.9g});"
        else:
            c = z.center / 1000
            ax = {"x": 0, "y": 1, "z": 2}[z.axis]
            p1, p2 = c.copy(), c.copy()
            p1[ax] -= z.H / 2000
            p2[ax] += z.H / 2000
            src = (f"source cylinderToCell; point1 ({p1[0]:.9g} {p1[1]:.9g} {p1[2]:.9g}); "
                   f"point2 ({p2[0]:.9g} {p2[1]:.9g} {p2[2]:.9g}); radius {z.D / 2000:.9g};")
        actions.append(f"    {{ name {nm}; type cellZoneSet; action new; {src} }}")
    write(case / "system" / "topoSetDict", "dictionary", "topoSetDict", "actions\n(\n" + "\n".join(actions) + "\n);\n")

    # --- physical properties
    write(case / "constant" / "transportProperties", "dictionary", "transportProperties", {
        "transportModel": "Newtonian", "nu": air["nu"], "beta": air["beta"], "TRef": T_c + 273.15,
        "Pr": air["Pr"], "Prt": 0.85})
    write(case / "constant" / "turbulenceProperties", "dictionary", "turbulenceProperties",
          {"simulationType": "laminar"})
    gz = -9.80665 if gravity == "1g" else 0.0       # standard gravity, CGPM 1901 (exact)
    write(case / "constant" / "g", "uniformDimensionedVectorField", "g",
          f"dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 {gz});\n")

    # --- sources
    srcs = zone_sources(m, R)
    fvopt_T, fvopt = {}, {"CO2": {}, "H2O": {}}
    src_log = {}
    for z in m.spec.get("zones") or []:
        s = srcs.get(z["name"])
        if not s:
            continue
        copies = s["copies"]
        names = [z["name"]] if copies == 1 else [p.name for p in m.zones if p.name.startswith(z["name"] + "_")]
        tot = s["total"]
        src_log[z["name"]] = {**tot, "copies": copies}
        for nm in names:
            q = 1.0 / len(names)
            if tot["heat_W"]:
                fvopt_T[f"heat_{nm}"] = {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone",
                                         "cellZone": nm, "volumeMode": "absolute",
                                         "sources": {"T": {"explicit": tot["heat_W"] * q / (air["rho"] * air["cp"]),
                                                           "implicit": 0}}}
            for sp, key, scale in (("CO2", "CO2_mol_s", 1e6), ("H2O", "H2O_mol_s", 1e3)):
                if tot[key]:
                    fvopt[sp][f"{sp}_{nm}"] = {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone",
                                               "cellZone": nm, "volumeMode": "absolute",
                                               "sources": {sp: {"explicit": tot[key] * q / c_air * scale, "implicit": 0}}}
    if fvopt_T:
        write(case / "constant" / "fvOptions", "dictionary", "fvOptions", fvopt_T)

    # --- fields
    T0 = T_c + 273.15
    # snappyHexMesh names region patches <surface>_<region>
    patches = [f"domain_{r}" for r in roles] + (["obstacles"] if has_obs else [])
    U_bc, p_bc, prgh_bc, T_bc, a_bc, S_bc = {}, {}, {}, {}, {}, {"CO2": {}, "H2O": {}}
    open_by_name = {o["name"]: o for o in m.openings}
    mem_by_name = {o["name"]: o for o in m.membranes}
    for pfull in patches:
        pch = pfull[len("domain_"):] if pfull.startswith("domain_") else pfull
        role = roles.get(pch, "wall")
        p_bc[pfull] = {"type": "calculated", "value": "uniform 0"}
        a_bc[pfull] = {"type": "calculated", "value": "uniform 0"}
        if role == "inlet":
            o = open_by_name[pch]
            Q = _mid(R(o["flow_L_min"], f"openings.{pch}.flow_L_min")) / 1000 / 60
            U_bc[pfull] = {"type": "flowRateInletVelocity", "volumetricFlowRate": Q, "value": "uniform (0 0 0)"}
            prgh_bc[pfull] = {"type": "fixedFluxPressure", "value": "uniform 0"}
            T_bc[pfull] = {"type": "fixedValue", "value": f"uniform {T0}"}
            S_bc["CO2"][pfull] = {"type": "fixedValue", "value": f"uniform {co2_0}"}
            S_bc["H2O"][pfull] = {"type": "fixedValue", "value": f"uniform {h2o_0}"}
        elif role == "outlet":
            U_bc[pfull] = {"type": "pressureInletOutletVelocity", "value": "uniform (0 0 0)"}
            prgh_bc[pfull] = {"type": "fixedValue", "value": "uniform 0"}
            T_bc[pfull] = {"type": "inletOutlet", "inletValue": f"uniform {T0}", "value": f"uniform {T0}"}
            for sp, c0 in (("CO2", co2_0), ("H2O", h2o_0)):
                S_bc[sp][pfull] = {"type": "inletOutlet", "inletValue": f"uniform {c0}", "value": f"uniform {c0}"}
        else:
            U_bc[pfull] = {"type": "noSlip"}
            prgh_bc[pfull] = {"type": "fixedFluxPressure", "value": "uniform 0"}
            T_bc[pfull] = {"type": "fixedValue", "value": f"uniform {T0}"}
            if role == "membrane":
                o = mem_by_name[pch]
                k = _mid(R(o["permeance_m_s"], f"membranes.{pch}.permeance_m_s"))
                delta = h / 1000 / 2
                for sp, D, c0 in (("CO2", D_CO2, co2_0), ("H2O", D_H2O, h2o_0)):
                    ext = _mid(R(o["outside"][sp], f"membranes.{pch}.outside.{sp}"))
                    f = 1.0 / (1.0 + D / (k * delta))
                    S_bc[sp][pfull] = {"type": "mixed", "refValue": f"uniform {ext}", "refGradient": "uniform 0",
                                     "valueFraction": f"uniform {f:.6g}", "value": f"uniform {c0}"}
            else:
                for sp in ("CO2", "H2O"):
                    S_bc[sp][pfull] = {"type": "zeroGradient"}
    write_field(case, "U", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)", U_bc, cls="volVectorField")
    write_field(case, "p", "[0 2 -2 0 0 0 0]", "uniform 0", p_bc)
    write_field(case, "p_rgh", "[0 2 -2 0 0 0 0]", "uniform 0", prgh_bc)
    write_field(case, "T", "[0 0 0 1 0 0 0]", f"uniform {T0}", T_bc)
    write_field(case, "alphat", "[0 2 -1 0 0 0 0]", "uniform 0", a_bc)
    write_field(case, "CO2", "[0 0 0 0 0 0 0]", f"uniform {co2_0}", S_bc["CO2"])
    write_field(case, "H2O", "[0 0 0 0 0 0 0]", f"uniform {h2o_0}", S_bc["H2O"])

    # --- numerics + function objects
    probes = [list(np.round(z.center / 1000, 9)) for z in m.zones] or [list(loc)]
    funcs = {}
    for sp, D in (("CO2", D_CO2), ("H2O", D_H2O)):
        fo = {"type": "scalarTransport", "libs": '("libsolverFunctionObjects.so")', "field": sp,
              "D": D, "nCorr": 1, "writeControl": "writeTime"}
        if fvopt[sp]:
            fo["fvOptions"] = fvopt[sp]
        funcs[f"transport_{sp}"] = fo
    funcs["probes"] = {"type": "probes", "libs": '("libsampling.so")', "writeControl": "timeStep",
                       "writeInterval": num.get("probe_every_steps", 10),
                       "fields": "(U T CO2 H2O)",
                       "probeLocations": foam.Raw("(" + " ".join(f"({p[0]} {p[1]} {p[2]})" for p in probes) + ")")}
    for nm in zone_names:
        funcs[f"zone_{nm}"] = {"type": "volFieldValue", "libs": '("libfieldFunctionObjects.so")',
                               "writeControl": "timeStep", "writeInterval": num.get("probe_every_steps", 10),
                               "writeFields": "false", "regionType": "cellZone", "name": nm,
                               "operation": "volAverage", "fields": "(T CO2 H2O)"}
    funcs["domainAvg"] = {"type": "volFieldValue", "libs": '("libfieldFunctionObjects.so")',
                          "writeControl": "timeStep", "writeInterval": num.get("probe_every_steps", 10),
                          "writeFields": "false", "regionType": "all", "operation": "volAverage",
                          "fields": "(T CO2 H2O)"}
    for o in m.openings:
        funcs[f"flux_{o['name']}"] = {"type": "surfaceFieldValue", "libs": '("libfieldFunctionObjects.so")',
                                     "writeControl": "timeStep", "writeInterval": num.get("probe_every_steps", 10),
                                     "writeFields": "false", "regionType": "patch", "name": f"domain_{o['name']}",
                                     "operation": "weightedAverage", "weightField": "phi",
                                     "fields": "(T CO2 H2O)"}
        funcs[f"flow_{o['name']}"] = {"type": "surfaceFieldValue", "libs": '("libfieldFunctionObjects.so")',
                                     "writeControl": "timeStep", "writeInterval": num.get("probe_every_steps", 10),
                                     "writeFields": "false", "regionType": "patch", "name": f"domain_{o['name']}",
                                     "operation": "sum", "fields": "(phi)"}
    funcs["minmax"] = {"type": "fieldMinMax", "libs": '("libfieldFunctionObjects.so")', "writeControl": "timeStep",
                       "writeInterval": num.get("probe_every_steps", 10), "mode": "magnitude",
                       "fields": "(U T CO2 H2O)"}
    write(case / "system" / "controlDict", "dictionary", "controlDict", {
        "application": "buoyantBoussinesqPimpleFoam", "startFrom": "latestTime", "startTime": 0,
        "stopAt": "endTime", "endTime": num["end_time_s"], "deltaT": num.get("dt0_s", 1e-3),
        "writeControl": "adjustableRunTime", "writeInterval": num["write_every_s"], "purgeWrite": 0,
        "writeFormat": "binary", "writePrecision": 8, "writeCompression": "off", "timeFormat": "general",
        "timePrecision": 8, "runTimeModifiable": "true", "adjustTimeStep": "yes",
        "maxCo": num.get("max_co", 0.8), "maxDeltaT": num.get("max_dt_s", 1.0), "functions": funcs})
    write(case / "system" / "fvSchemes", "dictionary", "fvSchemes", {
        "ddtSchemes": {"default": "backward"},
        "gradSchemes": {"default": "Gauss linear"},
        "divSchemes": {"default": "none", "div(phi,U)": "Gauss linearUpwind grad(U)",
                       "div(phi,T)": "Gauss limitedLinear 1", "div(phi,CO2)": "Gauss limitedLinear 1",
                       "div(phi,H2O)": "Gauss limitedLinear 1",
                       "div((nuEff*dev2(T(grad(U)))))": "Gauss linear"},
        "laplacianSchemes": {"default": "Gauss linear limited corrected 0.5"},
        "interpolationSchemes": {"default": "linear"},
        "snGradSchemes": {"default": "limited corrected 0.5"},
    })
    write(case / "system" / "fvSolution", "dictionary", "fvSolution", {
        "solvers": {
            "p_rgh": {"solver": "GAMG", "smoother": "DIC", "tolerance": 1e-8, "relTol": 0.01},
            "p_rghFinal": {"solver": "GAMG", "smoother": "DIC", "tolerance": 1e-8, "relTol": 0},
            "\"(U|T|CO2|H2O)\"": {"solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-10, "relTol": 0},
            "\"(U|T|CO2|H2O)Final\"": {"solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-10,
                                        "relTol": 0},
        },
        "PIMPLE": {"momentumPredictor": "yes", "nOuterCorrectors": 1, "nCorrectors": 2,
                   "nNonOrthogonalCorrectors": 1, "pRefCell": 0, "pRefValue": 0},
    })
    write(case / "system" / "decomposeParDict", "dictionary", "decomposeParDict",
          {"numberOfSubdomains": nprocs, "method": "scotch"})
    meta = {"slug": slug, "gravity": gravity, "mesh": mesh, "cell_mm": h, "background_cells": int(np.prod(n)),
            "geometry": info, "physics": props, "initial": {"T_C": T_c, "CO2_ppm": co2_0, "H2O_mmol_mol": h2o_0},
            "sources_total": src_log, "provenance": m.provenance + R.used,
            "assumptions": m.spec.get("assumptions") or [], "numerics": num}
    (case / "case_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    return case


def mesh_case(case: Path, nprocs: int = 8):
    steps = ["blockMesh", "surfaceFeatureExtract", "snappyHexMesh -overwrite", "checkMesh", "topoSet"]
    foam.run(case, steps)
    log = (case / "log.checkMesh").read_text()
    if "Mesh OK" not in log:
        bad = [ln for ln in log.splitlines() if "***" in ln]
        raise foam.FoamError(f"{case.name}: checkMesh did not report 'Mesh OK':\n" + "\n".join(bad[:10]))


def solve(case: Path, nprocs: int = 8):
    if nprocs > 1:
        foam.run(case, ["decomposePar -force"])
        foam.run(case, ["par:buoyantBoussinesqPimpleFoam"], nprocs=nprocs)
        foam.run(case, ["reconstructPar -newTimes"])
    else:
        foam.run(case, ["buoyantBoussinesqPimpleFoam"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--gravity", choices=["0g", "1g"], default="0g")
    ap.add_argument("--mesh", choices=list(MESH_FACTOR), default="medium")
    ap.add_argument("--np", type=int, default=8)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--mesh-only", action="store_true")
    a = ap.parse_args(argv)
    case = build(a.slug, a.gravity, a.mesh, a.np)
    print(case)
    if a.run or a.mesh_only:
        mesh_case(case, a.np)
    if a.run:
        solve(case, a.np)


if __name__ == "__main__":
    main()
