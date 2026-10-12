#!/usr/bin/env python3
"""Fail if any output file is not described by a pattern in MANIFEST.tsv."""
import csv
import fnmatch
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pats = [r["pattern"] for r in csv.DictReader(open(root / "MANIFEST.tsv"), delimiter="\t")]
scope = ["data", "hardware", "models", "results", "latex/output"]
missing = []
for d in scope:
    for p in (root / d).rglob("*"):
        if p.is_file() and p.name != ".DS_Store":
            rel = p.relative_to(root).as_posix()
            if not any(fnmatch.fnmatch(rel, pat) for pat in pats):
                missing.append(rel)
for m in missing:
    print("UNDESCRIBED", m)
print("OK" if not missing else f"FAILED: {len(missing)} undescribed file(s)")
sys.exit(1 if missing else 0)
