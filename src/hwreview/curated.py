"""Stage 4c - tiers after targeted literature curation (hardware/<slug>.yaml).

Same critical items as the automated MI-CFD-HW checklist, judged on the curated,
sourced parameter records. A record counts only when its value is non-null and
not an 'n/a' placeholder (and, by the provenance test, carries a source + quote):

  G1  geometry.enclosure_internal_mm (or enclosure_cylinder_mm) - numeric, >= 2 dims
  G2  geometry.specimen_container_mm, or a specimen container/module/chamber volume
  F1  ventilation.mode
  F2  ventilation.flow_rate_L_min or air_velocity_m_s - waived when mode is sealed/passive
  E1  environment.temperature_C
  B1  specimen.type(s), or an organism named in a sourced specimen-unit record

Writes results/tables/T6_curated_tiers.csv.
"""
from __future__ import annotations

import re

import pandas as pd
import yaml

from .paths import HARDWARE, TABLES

CRIT = ["G1", "G2", "F1", "F2", "E1", "B1"]


def _ok(rec) -> bool:
    if not isinstance(rec, dict) or "value" not in rec:
        return False
    v = rec["value"]
    if v is None or (isinstance(v, str) and v.strip().lower().startswith("n/a")):
        return False
    return bool(rec.get("source"))


def _numeric(v, n=1) -> bool:
    if isinstance(v, (int, float)):
        return n <= 1
    if isinstance(v, list):
        return sum(isinstance(x, (int, float)) or (isinstance(x, list) and all(isinstance(y, (int, float)) for y in x))
                   for x in v) >= n
    return False


def _get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def assess(d: dict) -> dict:
    s = {}
    g1 = _get(d, "geometry.enclosure_internal_mm") or _get(d, "geometry.enclosure_cylinder_mm")
    s["G1"] = _ok(g1) and _numeric(g1["value"], 2)
    g2 = [_get(d, p) for p in ("geometry.specimen_container_mm", "geometry.specimen_container_volume_mL")]
    g2 += [v for k, v in (d.get("geometry") or {}).items()
           if re.search(r"(container|dish|module|chamber|cassette|bag|aquari|cage)\w*_(volume_)?(mL|cc|L)$", k)
           and not k.startswith("free_air")]
    s["G2"] = any(_ok(r) and (_numeric(r["value"]) or _numeric(r["value"], 2)) for r in g2 if r)
    mode = _get(d, "ventilation.mode")
    s["F1"] = _ok(mode)
    mval = str(mode.get("value", "")).lower() if s["F1"] else ""
    sealed = bool(re.search(r"sealed|passive|closed", mval)) and not re.search(r"forced|fan", mval)
    flow = [_get(d, p) for p in ("ventilation.flow_rate_L_min", "ventilation.air_velocity_m_s")]
    s["F2"] = sealed or any(_ok(r) and (_numeric(r["value"]) or _numeric(r["value"], 2)) for r in flow if r)
    s["F2_waived"] = sealed
    t = _get(d, "environment.temperature_C")
    s["E1"] = _ok(t) and (_numeric(t["value"]) or _numeric(t["value"], 2))
    s["B1"] = _ok(_get(d, "specimen.type")) or _ok(_get(d, "specimen.types"))
    if not s["B1"]:
        # organism named in a sourced specimen-unit record (value or verbatim quote)
        from .lexicon import ORG_RE, classes_in
        for path in ("geometry.n_specimen_units", "geometry.specimen_container", "geometry.layout"):
            r = _get(d, path)
            if _ok(r) and classes_in(f"{r.get('value')} {r.get('unit', '')} {r.get('quote', '')}", ORG_RE) - {"human"}:
                s["B1"] = True
                break
    crit = [s[k] for k in CRIT]
    s["tier"] = "A" if all(crit) else ("B" if sum(crit) >= 4 else "C")
    s["missing"] = "; ".join(k for k in CRIT if not s[k])
    s["ventilation_mode"] = mval
    return s


def run() -> pd.DataFrame:
    rows = []
    for f in sorted(HARDWARE.glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        a = assess(d)
        n_rec = n_src = 0

        def walk(node):
            nonlocal n_rec, n_src
            if isinstance(node, dict) and "value" in node:
                n_rec += 1
                n_src += _ok(node)
                return
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
        walk(d)
        rows.append({"slug": f.stem, "entity_id": d.get("entity_id"), "name": d.get("name"), **a,
                     "n_parameters": n_rec, "n_sourced": n_src})
    df = pd.DataFrame(rows)
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / "T6_curated_tiers.csv", index=False)
    return df


if __name__ == "__main__":
    d = run()
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(d[["slug", "tier", "missing", "ventilation_mode", "n_sourced", "n_parameters"]].to_string(index=False))
