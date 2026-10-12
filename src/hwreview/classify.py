"""Stage 3 - what each hardware entity is, what it can fly, where, and how it feeds specimens.

For every entity from the crosswalk this stage assigns

* role            habitat_growth | hosting_facility | processing_fixation |
                  analysis_instrument | sensor_dosimetry | exposure_facility |
                  ground_facility | nonbio | unknown
  (SPLASH category when present - a structured field - else keywords on the
  name and registry text; curated fixes in data/curated/role_overrides.csv)
* organism classes, from trusted text and from linked OSD studies
* bio_payload_capable  (biological specimens evidenced, role not nonbio/sensor/ground)
* platform / location classes, from payload missions (strong) and text (weak)
* nutrient / water delivery modes, each with a verbatim quote and URL

Outputs data/derived/classification.json, results/tables/T1_hardware_catalogue.csv,
T2_counts.csv and T2b_nutrient_evidence.csv.
"""
from __future__ import annotations

import json
import re
from collections import Counter

import pandas as pd

from . import crosswalk, sources
from .evidence import entity_missions, entity_studies, entity_texts
from .lexicon import LOC_RE, MODE_ORGANISMS, NONBIO_RE, NUT_RE, ORG_RE, classes_in, evidence
from .paths import CURATED, DERIVED, TABLES

CATEGORY_ROLE = [
    (r"plant growth|animal habitat|culturing|cell culture|incubator", "habitat_growth"),
    (r"biocubesat", "habitat_growth"),
    (r"fixation|sample handling|biological systems analysis", "processing_fixation"),
    (r"molecular biology|dna/rna|microscopy|plate read|imaging|search-for-life|physiology", "analysis_instrument"),
    (r"experiment hosting", "hosting_facility"),
    (r"exposure", "exposure_facility"),
    (r"dosimetry|spectroscopy", "sensor_dosimetry"),
    (r"physical science|materials science|fluid physics|combustion|thermodynamics|quantum|earth observation|"
     r"protein crystalli", "nonbio"),
]
NAME_ROLE = [
    (r"accelerator|synchrotron|reactor|gammacell|x-?rad|faxitron|sarrp|raraf|figaro|underground|"
     r"simulat|8 foot centrifuge|hindimb|hindlimb|warming box|anethesia|anesthesia|variable pressure growth|"
     r"biomass production chamber|aircraft", "ground_facility"),
    (r"dosimet|scintillat|radfet|tepc|pin diode|radiation (detector|source)|temperature record|recorder|"
     r"telemetry|measuring system|mass measurement|sensors?\b|camcorder|gas exchange measurement", "sensor_dosimetry"),
    (r"fixation|fixative|kfts?\b|activation pack|mixstix|transfer unit|access unit|freezer|refrigerator|"
     r"stowage|glove ?box|syringe|work station|dissecting", "processing_fixation"),
    (r"sequenc|minion|q?pcr|smartcycler|microscop|imager|plate reader|spectromet|densitometer|analy[sz]er|"
     r"biomole|tellas|wet ?lab|psychomotor", "analysis_instrument"),
    (r"habitat|greenhouse|plant growth|growth (chamber|unit|system|container)|cultivation|canister|incubator|"
     r"bioreactor|bioculture|cell culture|culture (module|model)|enclosure|cage|aquari|aquatic|holding facility|"
     r"garden|vegetable production|astroculture|nutrient delivery|xroots|tissue loss|fly (box|lab|kit)|"
     r"experiment package|containers?|egg|quail|cebas|cassette|bric|biotube|kubik|biorack|biopack|"
     r"rodent-bios|primate-bios|life support|bios\b|kit\b|chambers?|petri|substrate|powercell|nemaflex|"
     r"race tube|svet|lada|botex|plant experiment unit|tube packages?", "habitat_growth"),
    (r"rack|frame|black box|science(taxi|box|shell)|tangolab|centrifuge|variable-g|platform|drawer|"
     r"hermes|processor|apparatus|biokon|biolab|biological experiment laboratory|spectrum", "hosting_facility"),
    (r"exposure|external|misse|expose|biopan|exocube|oreocube|vault", "exposure_facility"),
]
MISSION_PLATFORM = [
    (r"^sts[- ]?\d+|^sl-?\d|spacelab|^iml|neurolab|^slj", "Shuttle"),
    (r"spacex|^spx|^crs|^ng-?\d|^orb-?\d|^oa-?\d|^htv|^soyuz|^progress|increment|expedition|^iss|"
     r"^ax-?\d|^ul?f\d|^\d+[ap]$|^hrf", "ISS"),
    (r"bion|cosmos|kosmos|biosatellite|foton", "Free-flyer (Bion/Cosmos/Biosatellite)"),
    (r"^mir|^nasa-mir", "Mir"),
    (r"^ns-?\d+|new shepard|spaceshiptwo|texus|maxus", "Suborbital"),
    (r"^ofo|orbiting frog", "Free-flyer (Bion/Cosmos/Biosatellite)"),
    (r"uavsar|aero science|^nasa \d+$|parabolic|kc-135|c-9", "Aircraft / parabolic"),
    (r"inc tbd", "ISS"),
    (r"skylab", "Skylab"),
    (r"apollo|gemini", "Apollo/Gemini"),
    (r"artemis|sls|orion", "Artemis/lunar"),
    (r"inspiration4|polaris|fram2", "Commercial free-flight crew"),
    (r"ground|nsrl|bnl|himac|ames|ksc", "Ground"),
]


DESC_ROLE = [
    (r"growth chamber|plant growth|grow(s|n|ing)? (plants|seedlings)|habitat for|houses? (the )?(animals|rats|mice|"
     r"frogs|fish|plants|cells)|incubat\w*|culture (chamber|vessel|module)|bioreactor|life[- ]support|"
     r"egg chamber|aquari|cages?\b|holding (unit|facility)", "habitat_growth"),
    (r"implant\w*|electrode|sensor|telemetry|record(s|er|ing) (temperature|data)|transducer|camera|monitor(s|ing) "
     r"(heart|blood|eeg|emg)", "sensor_dosimetry"),
    (r"fixat\w*|freez\w*|stor(e|age) (samples|specimens)|dissect\w*|preserv\w*", "processing_fixation"),
]


def _role(ent, sp) -> tuple[str, str]:
    if ent.get("kind") and ent["kind"] != "hardware":
        return ent["kind"], "curated platform kind"
    for sid in ent["splash_ids"]:
        cat = sp.loc[sid].get("category")
        if sources.is_informative(cat):
            for pat, role in CATEGORY_ROLE:
                if re.search(pat, cat, re.I):
                    return role, f"SPLASH category: {cat}"
    name = ent["canonical_name"]
    for pat, role in NAME_ROLE:
        if re.search(pat, name, re.I):
            return role, f"name keyword /{pat.split('|')[0]}.../"
    reg = sources.registry()
    for rid in ent["registry_ids"]:
        d = reg.loc[str(rid)]["description"] + " " + reg.loc[str(rid)]["components_text"]
        for pat, role in DESC_ROLE:
            m = re.search(pat, d, re.I)
            if m:
                return role, f"registry {rid} text: '{m.group(0)}'"
    return "experiment_unique_other", "no role keyword in name or registry text"


def _platforms(missions: list[str]) -> Counter:
    c = Counter()
    for m in missions:
        for pat, plat in MISSION_PLATFORM:
            if re.search(pat, m.strip(), re.I):
                c[plat] += 1
                break
        else:
            c["unmapped mission"] += 1
    return c


def load_role_overrides() -> dict:
    """node id (S<id> / R<id>) -> (role, reason)."""
    p = CURATED / "role_overrides.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p, comment="#").fillna("")
    return {r.node: (r.role, r.reason) for r in d.itertuples()}


def _override_for(e, ovr):
    for n in [f"S{i}" for i in e["splash_ids"]] + [f"R{i}" for i in e["registry_ids"]]:
        if n in ovr:
            return ovr[n]
    return None


def run():
    ents = crosswalk.load_entities()
    sp = sources.splash()
    ovr = load_role_overrides()
    rows, nut_rows = [], []
    for _, e in ents.iterrows():
        texts = entity_texts(e)
        e = e.copy()
        role, why = _role(e, sp)
        o = _override_for(e, ovr)
        if o:
            role, why = o[0], "curated: " + o[1]
        hw_texts = [t for t in texts if t.source != "study"]
        all_hw = " \n".join(t.text for t in hw_texts)
        # organisms: specimen-oriented fields only, to avoid e.g. 'crew' or 'cells' in electronics prose
        # payload descriptions describe a whole mission's complement, so they are excluded here
        spec_texts = [t for t in hw_texts if t.source in ("splash", "registry") and t.field in
                      ("specimen_types_supported", "name", "description", "components_text", "background",
                       "alternate_names")]
        org_text = set().union(*[classes_in(t.text, ORG_RE) for t in spec_texts]) if spec_texts else set()
        # 'human' only counts when SPLASH says the hardware takes human samples
        if "human" in org_text and not any(t.field == "specimen_types_supported" and classes_in(t.text, {"h": ORG_RE["human"]})
                                           for t in spec_texts):
            org_text.discard("human")
        studies = entity_studies(e)
        org_study = sorted({o for o in studies["organism"].dropna()})
        nonbio_hits = len(NONBIO_RE.findall(all_hw))
        missions = entity_missions(e)
        plats = _platforms(missions)
        loc_text = set()
        for t in hw_texts:
            if t.field in ("flight_heritage", "operations", "dims", "volume", "background", "description",
                           "components_text"):
                loc_text |= classes_in(t.text, LOC_RE)
        # nutrient modes, with the first verbatim quote per mode; only modes compatible
        # with an organism class the hardware carries are credited
        org_all = set(org_text) | set().union(*[classes_in(o, ORG_RE) for o in org_study]) if org_study else set(org_text)
        org_all |= {"plant"} if re.search(r"arabidopsis|thaliana|brassica|oryza|triticum|lactuca|solanum|capsicum|"
                                          r"brachypodium|zea|glycine|pisum|physcomitrella|ceratopteris",
                                          " ".join(org_study), re.I) else set()
        org_all |= {"rodent"} if re.search(r"mus musculus|rattus", " ".join(org_study), re.I) else set()
        org_all |= {"cell_tissue"} if re.search(r"homo sapiens", " ".join(org_study), re.I) else set()
        org_all |= {"microbe"} if re.search(r"bacill|escherichia|staphylo|pseudomonas|saccharomyces|aspergillus|"
                                            r"microbiota|salmonella|streptococcus|serratia|candida",
                                            " ".join(org_study), re.I) else set()
        org_all |= {"invertebrate"} if re.search(r"drosophila|caenorhabditis", " ".join(org_study), re.I) else set()
        modes = {}
        for t in sorted(texts, key=lambda t: {"study": 0, "payload": 1, "registry": 2, "splash": 3}[t.source]):
            for mode, rx in NUT_RE.items():
                if mode in modes or not (MODE_ORGANISMS[mode] & org_all):
                    continue
                q = evidence(t.text, rx)
                if q:
                    modes[mode] = (q, t)
        for mode, (q, t) in modes.items():
            nut_rows.append({"entity_id": e["entity_id"], "canonical_name": e["canonical_name"], "mode": mode,
                             "source": t.source, "record": t.record, "field": t.field, "url": t.url, "quote": q})
        bio = bool(org_text or org_study) and role not in (
            "nonbio", "sensor_dosimetry", "ground_facility", "vehicle_or_location", "ground_analog",
            "generic_or_unclear", "program")
        rows.append({
            "entity_id": e["entity_id"], "canonical_name": e["canonical_name"],
            "splash_ids": e["splash_ids"], "registry_ids": e["registry_ids"],
            "platform_strings": e["platform_strings"],
            "role": role, "role_basis": why,
            "organism_classes_text": sorted(org_text),
            "study_organisms": org_study,
            "organism_classes_all": sorted(org_all),
            "n_osd_studies": int(studies["osd"].nunique()),
            "osd_studies": sorted(studies["osd"].unique()),
            "study_link_routes": sorted(studies["route"].unique()),
            "bio_payload_capable": bio,
            # CFD-relevant: hardware in which live specimens are housed during flight. Hosting
            # facilities count when they carry organisms (EMCS, Kubik, Biolab, CBEF ...).
            "specimen_habitat": bio and role in ("habitat_growth", "hosting_facility"),
            "nonbio_term_hits": nonbio_hits,
            "missions": missions,
            "platforms_from_missions": dict(plats),
            "location_classes_text": sorted(loc_text),
            "nutrient_modes": sorted(modes),
            "splash_status": "; ".join(str(sp.loc[s].get("status") or "") for s in e["splash_ids"]),
            "splash_category": "; ".join(str(sp.loc[s].get("category") or "") for s in e["splash_ids"]),
            "first_launch": "; ".join(str(sp.loc[s].get("date_of_first_launch") or "") for s in e["splash_ids"]),
            "n_text_units": len(texts),
        })
    cls = pd.DataFrame(rows)
    DERIVED.mkdir(parents=True, exist_ok=True)
    cls.to_json(DERIVED / "classification.json", orient="records", indent=1)
    TABLES.mkdir(parents=True, exist_ok=True)
    flat = cls.copy()
    for c in flat.columns:
        if flat[c].map(lambda v: isinstance(v, (list, dict))).any():
            flat[c] = flat[c].map(lambda v: json.dumps(v) if isinstance(v, dict) else "; ".join(map(str, v))
                                  if isinstance(v, list) else v)
    flat.to_csv(TABLES / "T1_hardware_catalogue.csv", index=False)
    pd.DataFrame(nut_rows).to_csv(TABLES / "T2b_nutrient_evidence.csv", index=False)
    counts = summarise(cls)
    counts.to_csv(TABLES / "T2_counts.csv", index=False)
    return cls, counts


def summarise(cls: pd.DataFrame) -> pd.DataFrame:
    out = []

    def add(group, key, n):
        out.append({"group": group, "key": key, "n": int(n)})
    add("total", "hardware entities", len(cls))
    add("total", "in SPLASH", (cls.splash_ids.map(len) > 0).sum())
    add("total", "in OSDR registry", (cls.registry_ids.map(len) > 0).sum())
    add("total", "named by >=1 OSD study platform field", (cls.platform_strings.map(len) > 0).sum())
    add("total", "linked to >=1 OSD study (any route)", (cls.n_osd_studies > 0).sum())
    for r, n in cls.role.value_counts().items():
        add("role", r, n)
    bio = cls[cls.bio_payload_capable]
    add("bio", "bio-payload capable", len(bio))
    add("bio", "specimen habitats (live specimens housed in flight)", cls.specimen_habitat.sum())
    add("bio", "bio-capable with >=1 OSD study", (bio.n_osd_studies > 0).sum())
    oc = Counter(c for v in bio.organism_classes_text for c in v)
    for k, n in sorted(oc.items()):
        add("organism class (text)", k, n)
    pc = Counter(p for d in bio.platforms_from_missions for p in d)
    for k, n in sorted(pc.items()):
        add("platform (missions, bio-capable)", k, n)
    lc = Counter(p for v in bio.location_classes_text for p in v)
    for k, n in sorted(lc.items()):
        add("location (text, bio-capable)", k, n)
    hab = cls[cls.specimen_habitat]
    nc = Counter(m for v in hab.nutrient_modes for m in v)
    for k, n in sorted(nc.items()):
        add("nutrient mode (habitats)", k, n)
    add("nutrient mode (habitats)", "none evidenced", (hab.nutrient_modes.map(len) == 0).sum())
    return pd.DataFrame(out)


if __name__ == "__main__":
    c, n = run()
    with pd.option_context("display.max_rows", 200, "display.width", 200):
        print(n.to_string(index=False))
