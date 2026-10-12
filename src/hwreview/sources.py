"""Load the frozen snapshot into tidy pandas tables.

Placeholder strings ("N/A", "Unknown", "TBD", "-", "None", ...) are treated
as *missing*: a field that says "Unknown" carries no information for a
modeller, so it must not count toward metadata completeness.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .paths import snapshot_dir

PLACEHOLDER = re.compile(
    r"^\s*(n/?a|na|none|null|unknown|tbd|tbc|-+|—|\?|not applicable|not available|"
    r"varies|varies by experiment|depends on experiment needs|depends on sample prep|"
    r"various|multiple|all)\s*\.?\s*$",
    re.I,
)


def is_informative(v) -> bool:
    if v is None or (isinstance(v, float) and v != v):
        return False
    if isinstance(v, (list, tuple)):
        return any(is_informative(x) for x in v)
    s = str(v).strip()
    return bool(s) and not PLACEHOLDER.match(s)


def _load(rel: str, snap: Path | None = None):
    return json.loads(((snap or snapshot_dir()) / rel).read_text())


@lru_cache(maxsize=None)
def splash(snap: str | None = None) -> pd.DataFrame:
    """SPLASH instruments, one row per _id (header row dropped)."""
    rows = _load("splash/instruments.json", Path(snap) if snap else None)
    df = pd.DataFrame([r for r in rows if str(r.get("_id")) != "0"])
    df["_id"] = df["_id"].astype(int)
    return df.sort_values("_id").set_index("_id", drop=False)


@lru_cache(maxsize=None)
def splash_header(snap: str | None = None) -> dict:
    rows = _load("splash/instruments.json", Path(snap) if snap else None)
    return next(r for r in rows if str(r.get("_id")) == "0")


@lru_cache(maxsize=None)
def registry(snap: str | None = None) -> pd.DataFrame:
    recs = _load("registry/hardware.json", Path(snap) if snap else None)
    out = []
    for hid, r in recs.items():
        r = r or {}
        parents = r.get("parents") or {}
        payloads = sorted({p["payload"].rstrip("/").rsplit("/", 1)[-1]
                           for p in parents.get("payload") or [] if p.get("payload")})
        exps = sorted({e["experiment"].rstrip("/").rsplit("/", 1)[-1]
                       for e in parents.get("experiment") or [] if e.get("experiment")})
        comps = r.get("components") or []
        out.append({
            "reg_id": str(hid),
            "name": (r.get("name") or "").strip(),
            "description": r.get("description") or "",
            "components_text": " | ".join(f"{c.get('name', '')}: {c.get('description', '')}" for c in comps),
            "n_components": len(comps),
            "payloads": payloads,
            "experiments": exps,
        })
    return pd.DataFrame(out).set_index("reg_id", drop=False)


@lru_cache(maxsize=None)
def payloads(snap: str | None = None) -> dict:
    return _load("registry/payload.json", Path(snap) if snap else None)


@lru_cache(maxsize=None)
def experiments(snap: str | None = None) -> dict:
    return _load("registry/experiment.json", Path(snap) if snap else None)


@lru_cache(maxsize=None)
def study_platforms(snap: str | None = None) -> pd.DataFrame:
    """One row per (dataset, organism) from the biodata platform query."""
    rows = _load("biodata/datasets_platform.json", Path(snap) if snap else None)
    df = pd.DataFrame(rows).rename(columns={
        "id.accession": "osd",
        "investigation.study.comment.experiment platform": "platform",
        "investigation.study.comment.project identifier": "project_id",
        "study.characteristics.organism": "organism",
    })
    for c in ("platform", "project_id", "organism"):
        df[c] = df[c].astype(object).where(df[c].map(is_informative), None)
        df[c] = df[c].map(lambda s: s.strip() if isinstance(s, str) else s)
    return df


@lru_cache(maxsize=None)
def dataset_metadata(snap: str | None = None) -> dict:
    return _load("biodata/dataset_metadata.json", Path(snap) if snap else None)
