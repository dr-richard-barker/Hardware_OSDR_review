"""Assemble, per hardware entity, every piece of *trusted* source text.

Each text unit keeps its provenance (source, record id, field, URL) so any
classification can be traced to a verbatim quote. SPLASH fields judged
misattributed / uncertain / duplicate in data/curated/splash_field_review.csv
are excluded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd
import yaml

from . import sources
from .paths import CURATED

SPLASH_URL = "https://visualization.osdr.nasa.gov/splash-api/public/instruments/{}"
REG_URL = "https://osdr.nasa.gov/geode-py/ws/api/hardware/{}"
PAY_URL = "https://osdr.nasa.gov/geode-py/ws/api/payload/{}"
OSD_URL = "https://visualization.osdr.nasa.gov/biodata/api/v2/dataset/{}/"

SPLASH_TEXT_FIELDS = ["name", "background", "specimen_types_supported", "specimen_size", "dims",
                      "volume", "flight_heritage", "operations", "lighting", "gas_control",
                      "rh_range", "temperature_range", "pressure", "measurements", "note_specs",
                      "category", "nutrient_production", "experiment_duration"]


@dataclass(frozen=True)
class Text:
    source: str      # splash | registry | payload | study
    record: str      # id within the source
    field: str
    url: str
    text: str


@lru_cache(maxsize=None)
def untrusted() -> frozenset[tuple[int, str]]:
    """(splash_id, field) pairs that must not be used: curated verdicts + the displaced block."""
    out = set()
    p = CURATED / "splash_field_review.csv"
    if p.exists():
        d = pd.read_csv(p)
        d = d[d["verdict"].isin(["misattributed", "uncertain", "duplicate_of"])]
        out |= set(zip(d["splash_id"].astype(int), d["field"]))
    b = CURATED / "splash_block_rule.yaml"
    if b.exists():
        rule = yaml.safe_load(b.read_text())
        sp = sources.splash()
        for i in range(rule["first_id"], rule["last_id"] + 1):
            if i in sp.index:
                out |= {(i, f) for f in sp.columns if f not in rule["keep"]}
    # background of a record that describes another instrument cannot anchor it either
    if p.exists():
        d = pd.read_csv(p)
        out |= set(zip(d.loc[d.verdict == "duplicate_of", "splash_id"].astype(int),
                       d.loc[d.verdict == "duplicate_of", "field"]))
    return frozenset(out)


def osd_from_url(u: str) -> str | None:
    m = re.search(r"/osd/meta/(\d+)", u or "")
    return f"OSD-{m.group(1)}" if m else None


def payload_info(pid: str) -> dict:
    p = sources.payloads().get(pid) or {}
    missions = p.get("missions") or []
    if isinstance(missions, dict):
        missions = [missions]
    studies = []
    for g in (p.get("parents") or {}).get("GLDS_Study") or []:
        u = g.get("GLDS_Study") if isinstance(g, dict) else g
        o = osd_from_url(u)
        if o:
            studies.append(o)
    hw = p.get("hardware") or []
    if isinstance(hw, dict):
        hw = [hw]
    orgs = []
    for sg in p.get("subjectGroups") or []:
        sn = (sg or {}).get("scientificName") or {}
        if isinstance(sn, dict) and sn.get("annotationValue"):
            orgs.append(sn["annotationValue"])
    return {"payload": pid, "name": p.get("payloadName") or "", "description": p.get("description") or "",
            "missions": [m.get("identifier") for m in missions if m.get("identifier")],
            "mission_dates": [(m.get("startDate"), m.get("endDate")) for m in missions],
            "studies": sorted(set(studies)),
            "hardware_versions": [(h.get("link", ""), h.get("versionName") or "", h.get("versionDescription") or "")
                                  for h in hw],
            "organisms": sorted(set(orgs))}


def entity_texts(ent: pd.Series, include_studies: bool = True) -> list[Text]:
    out: list[Text] = []
    sp = sources.splash()
    bad = untrusted()
    for sid in ent["splash_ids"]:
        r = sp.loc[sid]
        for f in SPLASH_TEXT_FIELDS:
            v = r.get(f)
            if (sid, f) in bad or not sources.is_informative(v):
                continue
            out.append(Text("splash", str(sid), f, SPLASH_URL.format(sid), str(v)))
        alt = r.get("alternate_names")
        if isinstance(alt, list) and alt:
            out.append(Text("splash", str(sid), "alternate_names", SPLASH_URL.format(sid), "; ".join(alt)))
    reg = sources.registry()
    for rid in ent["registry_ids"]:
        r = reg.loc[str(rid)]
        for f in ("name", "description", "components_text"):
            if r[f]:
                out.append(Text("registry", str(rid), f, REG_URL.format(rid), r[f]))
        for pid in r["payloads"]:
            pi = payload_info(pid)
            if pi["description"]:
                out.append(Text("payload", pid, "description", PAY_URL.format(pid), pi["description"]))
            for link, vn, vd in pi["hardware_versions"]:
                if link.rstrip("/").endswith(f"/{rid}") and (vn or vd):
                    out.append(Text("payload", pid, "hardware_version", PAY_URL.format(pid), f"{vn}: {vd}"))
    if include_studies:
        meta = sources.dataset_metadata()
        st = entity_studies(ent)
        # only studies whose own platform field names this hardware: payload-route studies
        # describe every hardware item on a mission and would contaminate the evidence
        for osd in st.loc[st["route"] == "platform", "osd"].unique():
            m = meta.get(osd) or {}
            prot = m.get("study protocol description")
            names = m.get("study protocol name")
            if isinstance(prot, list):
                for k, t in enumerate(prot):
                    nm = names[k] if isinstance(names, list) and k < len(names) else ""
                    if nm and re.search(r"growth|cultivation|husbandry|animal|plant|culture|flight|habitat",
                                        nm, re.I) and t:
                        out.append(Text("study", osd, f"protocol:{nm}", OSD_URL.format(osd), str(t)))
            elif prot:
                out.append(Text("study", osd, "protocol", OSD_URL.format(osd), str(prot)))
    return out


def entity_studies(ent: pd.Series) -> pd.DataFrame:
    """OSD studies linked to an entity, with the route that links them.

    route 'platform' : the study's own experiment-platform field names the hardware
    route 'payload'  : registry hardware -> payload -> GLDS_Study
    """
    plat = sources.study_platforms()
    rows = []
    for s in ent["platform_strings"]:
        for _, r in plat[plat["platform"] == s].iterrows():
            rows.append({"osd": r["osd"], "route": "platform", "organism": r["organism"]})
    reg = sources.registry()
    org_by_osd = _orgs_by_osd()
    for rid in ent["registry_ids"]:
        for pid in reg.loc[str(rid)]["payloads"]:
            for osd in payload_info(pid)["studies"]:
                orgs = org_by_osd.get(osd, []) or [None]
                for o in orgs:
                    rows.append({"osd": osd, "route": "payload", "organism": o})
    df = pd.DataFrame(rows, columns=["osd", "route", "organism"])
    return df.drop_duplicates()


@lru_cache(maxsize=None)
def _orgs_by_osd() -> dict:
    plat = sources.study_platforms()
    return {k: sorted({o for o in g if isinstance(o, str)}) for k, g in plat.groupby("osd")["organism"]}


def entity_missions(ent: pd.Series) -> list[str]:
    reg = sources.registry()
    ms = []
    for rid in ent["registry_ids"]:
        for pid in reg.loc[str(rid)]["payloads"]:
            ms += payload_info(pid)["missions"]
    return sorted(set(ms))
