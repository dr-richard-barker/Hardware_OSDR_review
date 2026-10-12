#!/usr/bin/env python3
"""Prepare a pandoc-friendly copy of the LaTeX manuscript.

* inlines \\input{...} files (the generated macros) and expands \\hw... macros to their
  values, so DOCX/HTML show exactly the numbers the PDF shows;
* points \\includegraphics at the PNG twin of each PDF figure;
* drops LaTeX-only layout commands pandoc cannot use.
"""
import re
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
text = src.read_text()
here = src.parent

macros = {}
for m in re.finditer(r"\\newcommand\{\\(hw\w+)\}\{(.*)\}", (here / "../results/macros.tex").read_text()):
    macros[m.group(1)] = m.group(2)
text = re.sub(r"\\input\{\.\./results/macros(\.tex)?\}\s*", "", text)


def _inline(m):
    f = here / (m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex")
    t = f.read_text() if f.exists() else ""
    # pandoc does not know adjustbox: keep only the tabular inside
    t = re.sub(r"\\begin\{adjustbox\}\{[^}]*\}\s*", "", t)
    return t.replace("\\end{adjustbox}", "")


text = re.sub(r"\\input\{([^}]*)\}", _inline, text)
# longest names first so \hwNHabitats is not clipped by \hwNHab
for name in sorted(macros, key=len, reverse=True):
    text = re.sub(rf"\\{name}(?![A-Za-z])(\{{\}})?", lambda _m, v=macros[name]: v, text)
leftover = sorted(set(re.findall(r"\\hw[A-Za-z]+", text)))
if leftover:
    sys.exit(f"undefined result macros: {leftover}")
text = re.sub(r"(\\includegraphics(?:\[[^\]]*\])?\{[^}]*?)\.pdf\}", r"\1.png}", text)
for cmd in (r"\\linenumbers", r"\\doublespacing", r"\\clearpage", r"\\FloatBarrier"):
    text = re.sub(cmd, "", text)
dst.write_text(text)
