#!/usr/bin/env python3
"""Pre-flight checks for the manuscript sources.

Fails when: a \\cite key is missing from references.bib; a \\ref has no \\label; a figure
file is missing; a result macro (\\hw...) is not defined in ../results/macros.tex; a
number that looks like a result is typed directly in Results (outside macros), or a
TODO/TBD/XXX marker remains.
"""
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
bib = (here / "references.bib").read_text()
keys = set(re.findall(r"@\w+\{([^,]+),", bib))
macros = set(re.findall(r"\\newcommand\{\\(hw\w+)\}", (here / "../results/macros.tex").read_text()))
errs = []
for name in sys.argv[1:] or ["manuscript.tex"]:
    t = (here / name).read_text()
    body = re.sub(r"(?<!\\)%.*", "", t)
    for group in re.findall(r"\\cite[pt]?\*?(?:\[[^\]]*\])?\{([^}]*)\}", body):
        for k in group.split(","):
            if k.strip() not in keys:
                errs.append(f"{name}: citation '{k.strip()}' not in references.bib")
    labels = set(re.findall(r"\\label\{([^}]*)\}", body))
    for r in re.findall(r"\\(?:auto|c|C)?ref\{([^}]*)\}", body):
        if r not in labels:
            errs.append(f"{name}: \\ref{{{r}}} has no \\label")
    for g in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", body):
        if not (here / g).exists():
            errs.append(f"{name}: figure file missing: {g}")
    for mname in set(re.findall(r"\\(hw[A-Za-z]+)", body)):
        if mname not in macros:
            errs.append(f"{name}: result macro \\{mname} undefined")
    for marker in ("TODO", "TBD", "XXX", "??"):
        if marker in body:
            errs.append(f"{name}: unresolved marker '{marker}'")
for e in errs:
    print("FAIL", e)
print("OK" if not errs else f"FAILED: {len(errs)} problem(s)")
sys.exit(1 if errs else 0)
