"""Stage 5 - parametric hardware geometry from a model spec (models/<slug>.yaml).

A model spec turns the sourced parameters of hardware/<slug>.yaml into
primitives. Every number in a model spec is either
  * {ref: <dotted path into hardware/<slug>.yaml>, index: k (optional), scale: s (optional)}
    -> resolved from the sourced value (provenance is kept), or
  * a literal, which MUST be listed under `assumptions:` with a reason
    (validate() refuses a spec with an unlisted literal).

Coordinates are millimetres; origin = domain minimum corner (box) or the centre
of the domain base (cylinder, axis z). Gravity acts along -z when switched on.

Primitives
  domain:     {shape: box, size: [Lx, Ly, Lz]} | {shape: cylinder, D:, H:}
  obstacles:  [{name, shape: box|cylinder, size|D,H, center: [x,y,z], axis: z,
                repeat: {n: [nx, ny, nz], pitch: [px, py, pz]}}]
  zones:      specimen zones, same shape vocabulary, + sources (see cases.py)
  openings:   [{name, role: inlet|outlet, face: xmin|xmax|ymin|ymax|zmin|zmax,
                size: [a, b], center: [u, v]}]   (rectangles on box faces)
  membranes:  [{name, face:, size:, center:, permeance_m_s: {ref:...}}] (patches)
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
import yaml

from .paths import HARDWARE, ROOT

import os

MODELS = Path(os.environ.get("HWREVIEW_MODELS", ROOT / "models"))
FACES = {"xmin": (0, -1), "xmax": (0, 1), "ymin": (1, -1), "ymax": (1, 1), "zmin": (2, -1), "zmax": (2, 1)}


# ----------------------------------------------------------------------------- spec
def _dig(d, path):
    for k in path.split("."):
        d = d[k]
    return d


class Resolver:
    """Resolve {ref: ...} values against the sourced hardware file, logging provenance."""

    def __init__(self, hw: dict, assumptions: list[dict]):
        self.hw, self.assumptions, self.used = hw, assumptions, []
        self.assumed = {a["param"] for a in assumptions}

    def __call__(self, v, where: str):
        if isinstance(v, dict) and "ref" in v:
            rec = _dig(self.hw, v["ref"])
            val = rec["value"] if isinstance(rec, dict) else rec
            if val is None:
                raise ValueError(f"{where}: {v['ref']} is null in the hardware file")
            if "index" in v:
                val = val[v["index"]]
            if "scale" in v:
                val = (np.asarray(val, float) * v["scale"]).tolist() if isinstance(val, list) else val * v["scale"]
            self.used.append({"where": where, "ref": v["ref"], "value": val,
                              "source": rec.get("source") if isinstance(rec, dict) else None})
            return val
        if isinstance(v, list):
            return [self(x, f"{where}[{k}]") for k, x in enumerate(v)]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if where not in self.assumed and not any(where.startswith(a + "[") or where.startswith(a + ".")
                                                     for a in self.assumed):
                raise ValueError(f"literal {v} at '{where}' is neither sourced (ref) nor a listed assumption")
        return v


@dataclass
class Prim:
    name: str
    shape: str
    center: np.ndarray
    size: np.ndarray | None = None      # box
    D: float | None = None              # cylinder
    H: float | None = None
    axis: str = "z"
    extra: dict = field(default_factory=dict)

    def mesh(self) -> trimesh.Trimesh:
        if self.shape == "box":
            m = trimesh.creation.box(extents=self.size)
        else:
            m = trimesh.creation.cylinder(radius=self.D / 2, height=self.H, sections=96)
            if self.axis != "z":
                ax = {"x": [0, 1, 0], "y": [1, 0, 0]}[self.axis]
                m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, ax))
        m.apply_translation(self.center)
        return m

    def bounds(self):
        return self.mesh().bounds


def _expand(items, R, kind):
    out = []
    for k, it in enumerate(items or []):
        w = f"{kind}[{k}]"
        rep = it.get("repeat")
        n = R(rep["n"], f"{w}.repeat.n") if rep else [1, 1, 1]
        pitch = np.asarray(R(rep["pitch"], f"{w}.repeat.pitch"), float) if rep else np.zeros(3)
        c0 = np.asarray(R(it["center"], f"{w}.center"), float)
        for i, j, l in itertools.product(*(range(int(x)) for x in n)):
            c = c0 + pitch * np.array([i, j, l])
            nm = it["name"] if np.prod(n) == 1 else f"{it['name']}_{i}{j}{l}"
            if it["shape"] == "box":
                out.append(Prim(nm, "box", c, size=np.asarray(R(it["size"], f"{w}.size"), float),
                                extra={k2: v for k2, v in it.items() if k2 in ("sources", "role")}))
            else:
                out.append(Prim(nm, "cylinder", c, D=float(R(it["D"], f"{w}.D")), H=float(R(it["H"], f"{w}.H")),
                                axis=it.get("axis", "z"),
                                extra={k2: v for k2, v in it.items() if k2 in ("sources", "role")}))
    return out


@dataclass
class Model:
    slug: str
    spec: dict
    hw: dict
    domain: Prim
    obstacles: list[Prim]
    zones: list[Prim]
    openings: list[dict]
    membranes: list[dict]
    provenance: list[dict]


def load(slug: str) -> Model:
    models_dir = Path(os.environ.get("HWREVIEW_MODELS", ROOT / "models"))
    spec = yaml.safe_load((models_dir / f"{slug}.yaml").read_text())
    hw_dir = Path(os.environ.get("HWREVIEW_HARDWARE", HARDWARE))
    hw = yaml.safe_load((hw_dir / f"{spec['hardware']}.yaml").read_text())
    R = Resolver(hw, spec.get("assumptions") or [])
    d = spec["domain"]
    if d["shape"] == "box":
        size = np.asarray(R(d["size"], "domain.size"), float)
        dom = Prim("domain", "box", size / 2, size=size)
    else:
        D, H = float(R(d["D"], "domain.D")), float(R(d["H"], "domain.H"))
        dom = Prim("domain", "cylinder", np.array([0, 0, H / 2]), D=D, H=H)
    obs = _expand(spec.get("obstacles"), R, "obstacles")
    zones = _expand(spec.get("zones"), R, "zones")
    opens = []
    for k, o in enumerate(spec.get("openings") or []):
        opens.append({**o, "size": R(o["size"], f"openings[{k}].size"), "center": R(o["center"], f"openings[{k}].center")})
    mems = []
    for k, o in enumerate(spec.get("membranes") or []):
        mems.append({**o, "size": R(o["size"], f"membranes[{k}].size"), "center": R(o["center"], f"membranes[{k}].center"),
                     "permeance_m_s": R(o["permeance_m_s"], f"membranes[{k}].permeance_m_s")})
    for k, c in enumerate(spec.get("physics", {}).items() if isinstance(spec.get("physics"), dict) else []):
        pass
    return Model(slug, spec, hw, dom, obs, zones, opens, mems, R.used)


def validate(m: Model) -> list[str]:
    """Geometric sanity: obstacles/zones inside the domain, openings on their face."""
    errs = []
    lo, hi = m.domain.bounds()
    for p in m.obstacles + m.zones:
        b = p.bounds()
        if np.any(b[0] < lo - 1e-6) or np.any(b[1] > hi + 1e-6):
            errs.append(f"{p.name} extends outside the domain: {b.round(2).tolist()} vs {[lo.tolist(), hi.tolist()]}")
    if m.domain.shape == "cylinder" and (m.openings or m.membranes):
        for o in m.openings + m.membranes:
            if o["face"] not in ("zmin", "zmax"):
                errs.append(f"{o['name']}: cylinder domains support openings on end caps only")
    for o in m.openings + m.membranes:
        ax, _ = FACES[o["face"]]
        uv = [a for a in range(3) if a != ax]
        for k, a in enumerate(uv):
            half = o["size"][k] / 2
            if o["center"][k] - half < lo[a] - 1e-6 or o["center"][k] + half > hi[a] + 1e-6:
                errs.append(f"{o['name']} does not fit on face {o['face']}")
    return errs


# ----------------------------------------------------------------------------- STL
def _global_cuts(lo, hi, patches_all):
    """Cut coordinates per axis shared by every face, so neighbouring faces share edge vertices."""
    cuts = [{lo[a], hi[a]} for a in range(3)]
    for p in patches_all:
        ax, _ = FACES[p["face"]]
        u, v = [a for a in range(3) if a != ax]
        (a_, b_), (cu, cv) = p["size"], p["center"]
        cuts[u] |= {cu - a_ / 2, cu + a_ / 2}
        cuts[v] |= {cv - b_ / 2, cv + b_ / 2}
    return [sorted(c) for c in cuts]


def _face_rects(lo, hi, face, patches, cuts):
    """Split a box face into rectangles tagged by patch name (default 'walls')."""
    ax, sgn = FACES[face]
    u, v = [a for a in range(3) if a != ax]
    us, vs = cuts[u], cuts[v]
    out = []
    for (u0, u1), (v0, v1) in itertools.product(zip(us[:-1], us[1:]), zip(vs[:-1], vs[1:])):
        mu, mv = (u0 + u1) / 2, (v0 + v1) / 2
        tag = "walls"
        for p in patches:
            (a, b), (cu, cv) = p["size"], p["center"]
            if abs(mu - cu) < a / 2 and abs(mv - cv) < b / 2:
                tag = p["name"]
        w = hi[ax] if sgn > 0 else lo[ax]
        quad = []
        for uu, vv in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
            pt = np.zeros(3)
            pt[ax], pt[u], pt[v] = w, uu, vv
            quad.append(pt)
        quad = np.array(quad)
        n = np.cross(quad[1] - quad[0], quad[2] - quad[0])
        if np.dot(n, np.eye(3)[ax] * sgn) < 0:
            quad = quad[::-1]
        out.append((tag, quad))
    return out


def _write_multisolid(path: Path, solids: dict[str, list[np.ndarray]]):
    """solids: name -> list of (3,3) triangles (mm). Written in metres."""
    with open(path, "w") as f:
        for name, tris in solids.items():
            f.write(f"solid {name}\n")
            for t in tris:
                t = np.asarray(t) / 1000.0
                n = np.cross(t[1] - t[0], t[2] - t[0])
                n = n / (np.linalg.norm(n) or 1)
                f.write(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n    outer loop\n")
                for p in t:
                    f.write(f"      vertex {p[0]:.9e} {p[1]:.9e} {p[2]:.9e}\n")
                f.write("    endloop\n  endfacet\n")
            f.write(f"endsolid {name}\n")


def write_stl(m: Model, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    solids: dict[str, list] = {}
    patch_roles = {"walls": "wall"}
    if m.domain.shape == "box":
        lo, hi = m.domain.bounds()
        cuts = _global_cuts(lo, hi, m.openings + m.membranes)
        for face in FACES:
            ps = [o for o in m.openings + m.membranes if o["face"] == face]
            for tag, q in _face_rects(lo, hi, face, ps, cuts):
                solids.setdefault(tag, []).extend([q[[0, 1, 2]], q[[0, 2, 3]]])
        for o in m.openings:
            patch_roles[o["name"]] = o["role"]
        for o in m.membranes:
            patch_roles[o["name"]] = "membrane"
    else:
        dm = m.domain.mesh()
        z0, z1 = dm.bounds[:, 2]
        caps = {"zmin": z0, "zmax": z1}
        for tri, nrm in zip(dm.triangles, dm.face_normals):
            tag = "walls"
            for o in m.openings + m.membranes:
                zc = caps[o["face"]]
                c = tri.mean(axis=0)
                if abs(c[2] - zc) < 1e-6 and np.all(np.abs(c[:2] - np.asarray(o["center"])) <= np.asarray(o["size"]) / 2):
                    tag = o["name"]
            solids.setdefault(tag, []).append(tri)
        for o in m.openings:
            patch_roles[o["name"]] = o["role"]
        for o in m.membranes:
            patch_roles[o["name"]] = "membrane"
    _write_multisolid(outdir / "domain.stl", solids)
    dom_area = sum(trimesh.triangles.area(np.asarray(t)).sum() for t in solids.values())
    obs_vol = 0.0
    if m.obstacles:
        obs_solids = {}
        for p in m.obstacles:
            mm = p.mesh()
            obs_vol += mm.volume
            obs_solids.setdefault(p.name.rsplit("_", 1)[0] if "_" in p.name else p.name, []).extend(list(mm.triangles))
        _write_multisolid(outdir / "obstacles.stl", obs_solids)
    dvol = m.domain.mesh().volume
    # closure / volume checks (OCC-style silent failures are caught here, not in snappy)
    dm_check = trimesh.Trimesh(*trimesh.util.append_faces(
        [np.asarray(t).reshape(-1, 3) for t in solids.values()],
        [np.arange(len(t) * 3).reshape(-1, 3) for t in solids.values()]), process=True)
    dm_check.merge_vertices()
    info = {"domain_volume_mm3": float(dvol), "obstacle_volume_mm3": float(obs_vol),
            "air_volume_L_nominal": float((dvol - obs_vol) / 1e6), "domain_area_mm2": float(dom_area),
            "domain_watertight": bool(dm_check.is_watertight), "patch_roles": patch_roles,
            "domain_volume_from_stl_mm3": float(abs(dm_check.volume))}
    if not info["domain_watertight"] or abs(info["domain_volume_from_stl_mm3"] - dvol) / dvol > 0.01:
        raise RuntimeError(f"{m.slug}: domain STL not closed or volume mismatch: {info}")
    return info


def inside_point(m: Model) -> np.ndarray:
    """A point inside the air volume (inside domain, outside obstacles and off-grid) in metres."""
    lo, hi = m.domain.bounds()
    obs = [p.mesh() for p in m.obstacles]
    dom = m.domain.mesh()
    rng = np.random.default_rng(7)
    for _ in range(20000):
        p = lo + (hi - lo) * rng.uniform(0.05, 0.95, 3)
        if dom.contains([p])[0] and not any(o.contains([p])[0] for o in obs):
            return (p + 1e-3 * rng.uniform(0.1, 0.9, 3)) / 1000.0
    raise RuntimeError("no free point found inside the domain")
