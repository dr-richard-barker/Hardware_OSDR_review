#!/usr/bin/env python3
"""Build the Zenodo deposit archive in dist/.

Includes code, tests, the frozen snapshot, curated files, models, results (tables,
figures, animations, reduced VTK fields), the LaTeX sources and built outputs, and the
licence/citation files. Excludes the virtual environment, raw OpenFOAM run directories
(runs/) and build intermediates. Writes dist/<name>.tar.gz plus dist/FILES.sha256.
"""
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
meta = json.loads((root / ".zenodo.json").read_text())
version = next((ln.split(":", 1)[1].strip() for ln in (root / "CITATION.cff").read_text().splitlines()
                if ln.startswith("version:")), "0.0.0")
name = f"Hardware_OSDR_review-v{version}"
INCLUDE = ["README.md", "LICENSE", "LICENSE-DATA.md", "CITATION.cff", ".zenodo.json", "MANIFEST.tsv", "Makefile",
           "requirements.txt", ".gitignore", "src", "scripts", "tests", "data", "hardware", "models", "results",
           "openfoam", "latex", "site"]
EXCLUDE_PARTS = {"__pycache__", "build", ".DS_Store", ".pytest_cache"}
dist = root / "dist"
dist.mkdir(exist_ok=True)
files = []
for item in INCLUDE:
    p = root / item
    if not p.exists():
        continue
    for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
        if f.is_file() and not (set(f.relative_to(root).parts) & EXCLUDE_PARTS):
            files.append(f)
commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
with open(dist / "FILES.sha256", "w") as fh:
    for f in files:
        fh.write(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(root)}\n")
out = dist / f"{name}.tar.gz"
with tarfile.open(out, "w:gz") as tf:
    for f in files:
        tf.add(f, arcname=f"{name}/{f.relative_to(root)}")
    tf.add(dist / "FILES.sha256", arcname=f"{name}/FILES.sha256")
size = out.stat().st_size / 1e6
print(f"{out} ({size:.1f} MB, {len(files)} files, git {commit[:10]})")
print(f"Deposit title: {meta['title']}")
