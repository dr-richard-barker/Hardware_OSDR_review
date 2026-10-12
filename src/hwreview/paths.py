"""Repository paths and snapshot selection."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CURATED = ROOT / "data" / "curated"
DERIVED = ROOT / "data" / "derived"
HARDWARE = ROOT / "hardware"
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"
FIELDS = ROOT / "results" / "fields"
RUNS = ROOT / "runs"


def snapshot_dir(date: str | None = None) -> Path:
    """Return the raw snapshot directory to read.

    Every analysis stage reads a frozen snapshot, never the live APIs. The
    snapshot is chosen by $HWREVIEW_SNAPSHOT, else the newest dated folder.
    """
    date = date or os.environ.get("HWREVIEW_SNAPSHOT")
    if date:
        d = RAW / date
        if not d.is_dir():
            raise FileNotFoundError(f"snapshot {d} does not exist")
        return d
    dated = sorted(p for p in RAW.iterdir() if p.is_dir() and p.name[:4].isdigit())
    if not dated:
        raise FileNotFoundError("no snapshot in data/raw; run `make fetch` first")
    return dated[-1]
