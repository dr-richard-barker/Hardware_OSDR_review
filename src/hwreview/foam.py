"""Minimal OpenFOAM (v2606, Docker) driver: write dictionaries, run utilities, read fields.

Lessons carried over from microgreen-chamber-cfd/doc/FIRST_RUN.md:
* the environment is activated by sourcing etc/bashrc - never /usr/bin/openfoam2606
  (that execs an interactive shell and silently skips the rest of the script);
* every utility's exit status is checked AND its log must contain 'End' - a solver
  that dies can still exit 0 through wrapper scripts;
* dictionaries are written whole from Python; nothing is edited in place with
  foamDictionary (which expands $variables).
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

import numpy as np

IMAGE = ("opencfd/openfoam-run@sha256:"
         "7ad9ee415db514ecfab39718200049fac21dad4c4385c185595c08237f44929b")  # v2606 arm64, pinned
BASHRC = "/usr/lib/openfoam/openfoam2606/etc/bashrc"


class FoamError(RuntimeError):
    pass


def header(cls: str, obj: str, location: str | None = None) -> str:
    loc = f'    location    "{location}";\n' if location else ""
    return ("FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
            f"    class       {cls};\n{loc}    object      {obj};\n}}\n\n")


def fmt(v, ind: int = 0) -> str:
    """Serialise a Python value as OpenFOAM dictionary syntax."""
    pad = "    " * ind
    if isinstance(v, dict):
        out = []
        for k, x in v.items():
            if isinstance(x, dict):
                out.append(f"{pad}{k}\n{pad}{{\n{fmt(x, ind + 1)}{pad}}}\n")
            elif isinstance(x, Raw) and x.block:
                out.append(f"{pad}{k}\n{x.text}\n")
            else:
                out.append(f"{pad}{k} {fmt(x)};\n")
        return "".join(out)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "(" + " ".join(fmt(x) for x in v) + ")"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, Raw):
        return v.text
    return str(v)


class Raw:
    """Verbatim OpenFOAM text (e.g. 'uniform (0 0 0)' or a whole list block)."""

    def __init__(self, text: str, block: bool = False):
        self.text, self.block = text, block


def write(path: Path, cls: str, obj: str, body: dict | str, location: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if isinstance(body, str) else fmt(body)
    path.write_text(header(cls, obj, location) + text + "\n// ************************************************************************* //\n")


def write_field(case: Path, name: str, dims: str, internal: str, bfs: dict, cls: str = "volScalarField") -> None:
    body = f"dimensions      {dims};\n\ninternalField   {internal};\n\nboundaryField\n{{\n"
    for patch, d in bfs.items():
        body += f"    {patch}\n    {{\n" + fmt(d, 2) + "    }\n"
    body += "}\n"
    write(case / "0" / name, cls, name, body, location='"0"'.strip('"'))


def run(case: Path, steps: list[str], nprocs: int = 1, timeout: float | None = None) -> None:
    """Run OpenFOAM utilities inside the pinned container, one log per step.

    Each step is 'app args'; for nprocs > 1 a step prefixed with 'par:' is run with
    mpirun -np nprocs ... -parallel. Fails on non-zero exit or a log without 'End'.
    """
    case = case.resolve()
    root = case.parent
    for step in steps:
        par = step.startswith("par:")
        cmd = step[4:] if par else step
        app = cmd.split()[0]
        tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", cmd)[:60]
        log = f"log.{tag}"
        inner = f"mpirun --oversubscribe -np {nprocs} {cmd} -parallel" if par and nprocs > 1 else cmd
        script = f". {BASHRC} >/dev/null 2>&1; cd /work/{case.name} && {inner} > {log} 2>&1"
        docker = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
                  "-e", "OMPI_MCA_btl_vader_single_copy_mechanism=none",
                  "-v", f"{root}:/work", "--entrypoint", "bash", IMAGE, "-c", script]
        r = subprocess.run(docker, timeout=timeout)
        text = (case / log).read_text(errors="replace") if (case / log).exists() else ""
        if r.returncode != 0 or ("FOAM FATAL" in text) or (app not in ("foamToVTK",) and not re.search(r"^End\b", text, re.M)
                                                          and app not in ("decomposePar", "reconstructPar")):
            tail = "\n".join(text.splitlines()[-25:])
            raise FoamError(f"{case.name}: '{cmd}' failed (exit {r.returncode})\n{tail}")


def read_internal(path: Path) -> np.ndarray:
    """Read the internalField of an ASCII OpenFOAM field file (scalar or vector)."""
    t = path.read_text()
    m = re.search(r"internalField\s+uniform\s+([^;]+);", t)
    if m:
        v = m.group(1).strip()
        return np.array([float(x) for x in v.strip("()").split()]) if v.startswith("(") else np.array([float(v)])
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*\n?(\d+)\s*\n?\(", t)
    if not m:
        raise ValueError(f"cannot parse {path}")
    kind, n = m.group(1), int(m.group(2))
    body = t[m.end():]
    if kind == "scalar":
        vals = np.fromstring(body[:body.index(")\n;")] if ")\n;" in body else body.split(")")[0], sep="\n")
        return vals[:n]
    rows = re.findall(r"\(([^()]+)\)", body)[:n]
    return np.array([[float(x) for x in r.split()] for r in rows])


def time_dirs(case: Path) -> list[str]:
    out = []
    for p in case.iterdir():
        if p.is_dir():
            try:
                float(p.name)
                out.append(p.name)
            except ValueError:
                pass
    return sorted(out, key=float)
