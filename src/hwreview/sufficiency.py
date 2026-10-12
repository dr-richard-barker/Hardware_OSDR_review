"""Stage 4a - CFD minimum-information checklist (MI-CFD-HW) and tiers.

To build a defensible CFD model of a specimen environment you need, at minimum,
the 15 items below. Each item is scored 0 (absent), 0.5 (qualitative only:
a yes/no flag or a standard envelope such as 'middeck locker') or 1
(quantitative or explicit), with the verbatim quote that earned the score.

Two scopes are scored separately so the meta-analysis can show what the
catalogues alone support:

  splash   SPLASH record(s) only (trusted fields)
  public   SPLASH + OSDR registry + payload records + linked study protocols

Tier (computed on the 'public' scope plus any curated hardware/<slug>.yaml):
  A  CFD-ready   - every CRITICAL item scores 1
  B  partial     - every critical item >= 0.5
  C  insufficient
Only Tier A is modelled; Tier B/C appear in the gap analysis with the
blocking items listed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from . import crosswalk
from .evidence import Text, entity_texts
from .paths import DERIVED, TABLES

NUM = r"\d+(?:[.,]\d+)?"
U_LEN = r"(?:mm|cm|m|in(?:ch(?:es)?)?|\"|”)"
DIM3 = rf"\b{NUM}\s*{U_LEN}?\s*[x×X]\s*{NUM}\s*{U_LEN}?\s*[x×X]\s*{NUM}\s*{U_LEN}"
DIM_LWH = rf"\b{NUM}\s*(?:cm|mm)?\s*[LWD]\b.{{0,8}}{NUM}\s*(?:cm|mm)?\s*[WHD]\b"
ENVELOPE = (r"\b(?:middeck locker|mid-deck locker|locker|express rack|rack drawer|drawer|isis drawer|"
            r"quad[- ]locker|single locker|double locker|cubesat)\b|\b\d+\s*U\b")

# Sentences about sample preparation, storage or analysis describe the lab, not the
# flight environment; they are dropped before scoring (study protocols and payload prose).
PREP = re.compile(r"\b(stor(ed|age)|froz(en)?|freez\w*|-80|−80|thaw\w*|fixat\w*|fixed|rnalater|bleach|"
                  r"ethanol|hcl|sterili[sz]\w*|autoclav\w*|centrifug\w*|extract\w*|lysis|lysed|sequenc\w*|"
                  r"librar(y|ies)|pcr|dissect\w*|euthani[sz]\w*|harvest\w*|homogeni[sz]\w*|qiagen|kit\b|"
                  r"reagent|buffer|stain\w*|antibod\w*|microscop\w*|imaged|assay|pellet(ed)?|vortex\w*|"
                  r"anesthe\w*|necrops\w*|carcass|blood collect\w*|ground control)\b", re.I)
SENT = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    group: str
    full: str            # regex scoring 1
    half: str | None     # regex scoring 0.5
    fields: tuple = ()   # restrict to these fields (empty = any)
    critical: bool = False
    check: object = None  # optional validator(match) -> bool for 'full' matches


def _temp_ok(m: re.Match) -> bool:
    nums = [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", m.group(0))]
    return bool(nums) and all(0 <= v <= 45 for v in nums[:2])


def _dims_ok(m: re.Match) -> bool:
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", m.group(0))]
    return len(nums) >= 2 and all(v > 0 for v in nums)


ITEMS = [
    Item("G1", "Enclosure dimensions", "geometry", rf"{DIM3}|{DIM_LWH}", ENVELOPE, critical=True,
         check=_dims_ok),
    Item("G2", "Specimen-chamber volume or dimensions", "geometry",
         rf"\b{NUM}\s*(?:mm|cm)\s*(?:diameter\s*)?(?:round\s*|square\s*)?(?:petri|dish|plate|canister|tube|chamber|"
         rf"aquari\w*|cage|cassette|container|well)|(?:chamber|canister|cassette|container|aquari\w*|cage|bioreactor|"
         rf"reservoir|habitat|volume)\w*\s*(?:\w+\s*){{0,4}}(?:of|is|:|~|≈|about|approximately)?\s*{NUM}\s*"
         r"(?:ml|mL|l|L|liters?|litres?|cm3|cm³|m3|m³)\b|\b\d+(?:[.,]\d+)?\s*(?:ml|mL|l|L|liters?|litres?|cm3|cm³)\s+"
         r"(?:\w+\s*){0,3}(?:chamber|canister|cassette|container|aquari\w*|cage|bioreactor|reservoir|volume|capacity)",
         r"\b(chamber|canister|petri|dish|cassette|aquari\w*|cage|container)s?\b", critical=True),
    Item("G3", "Specimen layout / number of units", "geometry",
         rf"\b{NUM}\s*(?:plants?|mice|rats?|animals?|dishes|petri dishes|plates?|pillows?|canisters?|wells?|cassettes?|"
         r"containers?|aquaria|chambers?|tubes?|trays?|bags?|cartridges?|bioreactors?|cages?|seeds|seedlings|frogs?|"
         r"fish|quadrants?|compartments?|modules?)\b",
         r"\b(rows?|columns?|array|grid|arranged)\b"),
    Item("F1", "Ventilation mode (forced / passive / sealed)", "flow",
         r"\b(fans?|blowers?|forced[- ]air|recirculat\w*|air ?flow|airflow|ventilat\w*|sealed|hermetic\w*|"
         r"air[- ]?tight|closed (system|environment|container|canister)|passive gas exchange|purg(e|ed|ing)|"
         r"vented|vents)\b",
         r"\b(air (filtration|supply|exchange)|atmosphere|gas exchange)\b", critical=True),
    Item("F2", "Airflow rate or velocity", "flow",
         rf"\b{NUM}\s*(?:m/s|cm/s|mm/s|m s-1|m s−1|cm s-1|l/min|L/min|lpm|slpm|sccm|cfm|ach|air changes|"
         r"l/h|L/h|l/hr|liters per minute|litres per minute)(?![\w/])|wind speed",
         None, critical=True),
    Item("E1", "Temperature at specimen", "environment",
         rf"\b{NUM}\s*(?:-|–|to)\s*{NUM}\s*°?\s*C\b|(?<![-−\d]){NUM}\s*(?:±\s*{NUM}\s*)?°\s*C\b|"
         rf"(?<![-−\d]){NUM}\s*(?:deg(?:rees)?\.?\s*)C\b|(?<![-−\d]){NUM}C\b",
         r"\b(ambient|cabin temperature|temperature[- ]controlled|thermal control|temperature control\w*)\b",
         critical=True, check=_temp_ok),
    Item("E2", "Relative humidity", "environment",
         rf"\b{NUM}\s*%\s*(?:rh|relative humidity|humidity)\b|\b(?:rh|relative humidity|humidity)\s*(?:of|:|=|at|range)?\s*"
         rf"(?:~|≈)?\s*{NUM}(?:\s*(?:-|–|to)\s*{NUM})?\s*%|\b{NUM}\s*(?:-|–)\s*{NUM}\s*%",
         r"\bhumidity\b", fields=()),
    Item("E3", "Gas composition / CO2-O2 control", "environment",
         rf"\b{NUM}\s*(?:-|–)?\s*(?:{NUM}\s*)?ppm\b|\b{NUM}\s*%\s*(?:co2|o2|oxygen|carbon dioxide)\b|"
         r"\bco2 (?:set ?point|level|concentration)\w* (?:of|was|at)\b|\bscrubber|\blioh\b|lithium hydroxide|"
         r"\bco2 (?:control|injection)\b",
         r"\b(co2|co₂|carbon dioxide|oxygen|o2|gas control|gas exchange|gas supply)\b"),
    Item("E4", "Pressure", "environment",
         rf"\b{NUM}\s*(?:atm|kpa|psi[ag]?|torr|mbar|hpa)\b", r"\b(cabin pressure|ambient pressure|pressuri[sz]ed)\b"),
    Item("E5", "Lighting (type, flux or darkness)", "environment",
         rf"\b{NUM}\s*(?:µmol|umol|μmol|micromol)\b|\bppfd\b|\b{NUM}\s*lux\b|\bdark(ness)?[- ](grown|condition\w*)\b|"
         r"\bin (complete |total |constant )?darkness\b|\bno light\b|\bconstant dark\b",
         r"\b(leds?|light(ing|s)?|illuminat\w*|lamps?|photoperiod)\b"),
    Item("B1", "Specimen types", "biology",
         r"\b(arabidopsis|mice|mouse|rats?|medaka|zebrafish|drosophila|c\.? ?elegans|e\.? ?coli|yeast|lettuce|wheat|"
         r"mizuna|tomato|pepper|frogs?|newts?|quail|cells?|bacteri\w*|fung\w*|plants?|seedlings?|microbes?|"
         r"microorganisms?|fish|rodents?|worms?|insects?|algae|tissues?)\b",
         None, fields=("specimen_types_supported", "description", "components_text", "background",
                       "hardware_version", "protocol"), critical=True),
    Item("B2", "Nutrient / water delivery", "biology",
         r"\b(agar|phyta-?agar|phytagel|arcillite|calcined clay|turface|hydroponic\w*|aeroponic\w*|nutrient solution|"
         r"culture medi(um|a)|growth medi(um|a)|food ?bars?|nutribloc|lixits?|water (reservoir|delivery|injection|bag)|"
         r"medi(um|a) perfusion|fertili[sz]er|osmocote|feed(er|ing)|murashige|broth|plant pillows?)\b",
         r"\b(water|nutrients?|food)\b"),
    Item("B3", "Specimen gas-exchange / metabolic load", "biology",
         rf"\b{NUM}\s*(?:µmol|umol|μmol)\s*(?:co2|o2)\s*m-?2\s*s-?1|\b{NUM}\s*(?:ml|mL)\s*(?:o2|co2)\s*/?\s*(?:min|h)\b|"
         r"\b(respiration|photosynthetic|transpiration|metabolic) rates? (of|was|were)\b",
         r"\b(respiration|photosynthe\w*|transpiration|metabolic rate|gas exchange rate)\b"),
    Item("T1", "Heat load / power", "thermal",
         rf"(?:power|consum\w*|dissipat\w*|heat load|draw\w*|watts?)\D{{0,40}}{NUM}\s*(?-i:W|kW)\b|"
         rf"\b{NUM}\s*(?-i:W|kW)\b(?=\s*(?:\(|of|average|peak|max|nominal|power|continuous))|\b{NUM}\s*watts?\b",
         r"\b(heat (sink|exchanger|rejection)|cold ?plate|thermoelectric|peltier)\b", fields=()),
    Item("W1", "Wall / membrane gas permeability", "boundary",
         r"\b(gas[- ]permeable|breathable|micropore|membranes?|filter (cap|patch)|tyvek|gore-?tex|semi-?permeable|"
         r"permeable)\b",
         r"\b(polycarbonate|aluminium|aluminum|stainless|lexan|acrylic|teflon)\b"),
]
CRITICAL = [i.key for i in ITEMS if i.critical]


def _compile(p):
    return re.compile(p, re.I) if p else None


_RX = {i.key: (_compile(i.full), _compile(i.half)) for i in ITEMS}


def _quote(text: str, m: re.Match, w: int = 60) -> str:
    a, b = max(0, m.start() - w), min(len(text), m.end() + w)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")


def _units(texts: list[Text]):
    """Yield (Text, sentence) pairs; prose from studies/payloads is filtered for lab-prep sentences."""
    for t in texts:
        if t.source in ("study", "payload"):
            for sent in SENT.split(t.text):
                if not PREP.search(sent):
                    yield t, sent
        else:
            yield t, t.text


def score_texts(texts: list[Text]) -> dict:
    units = list(_units(texts))
    out = {}
    for it in ITEMS:
        full, half = _RX[it.key]
        best = (0.0, None, None)
        for t, txt in units:
            if it.fields and not any(t.field.startswith(f) for f in it.fields):
                continue
            hit = None
            for m in full.finditer(txt):
                if it.check is None or it.check(m):
                    hit = m
                    break
            if hit:
                best = (1.0, _quote(txt, hit), t)
                break
            if half and best[0] < 0.5:
                m = half.search(txt)
                if m:
                    best = (0.5, _quote(txt, m), t)
        s, q, t = best
        out[it.key] = {"score": s, "quote": q, "source": t.source if t else None,
                       "record": t.record if t else None, "field": t.field if t else None,
                       "url": t.url if t else None}
    return out


def tier(scores: dict[str, float]) -> str:
    crit = [scores[k] for k in CRITICAL]
    if all(s >= 1 for s in crit):
        return "A"
    if all(s >= 0.5 for s in crit):
        return "B"
    return "C"


def run():
    ents = crosswalk.load_entities()
    cls = pd.read_json(DERIVED / "classification.json", orient="records")
    cls = cls.set_index("entity_id")
    rows, ev = [], []
    for _, e in ents.iterrows():
        texts = entity_texts(e)
        scopes = {"splash": [t for t in texts if t.source == "splash"], "public": texts}
        rec = {"entity_id": e["entity_id"], "canonical_name": e["canonical_name"]}
        for scope, tx in scopes.items():
            sc = score_texts(tx)
            for k, v in sc.items():
                rec[f"{scope}_{k}"] = v["score"]
                if scope == "public":
                    ev.append({"entity_id": e["entity_id"], "item": k, **v})
            vals = {k: v["score"] for k, v in sc.items()}
            rec[f"{scope}_completeness"] = round(sum(vals.values()) / len(ITEMS), 4)
            rec[f"{scope}_critical"] = round(sum(vals[k] for k in CRITICAL) / len(CRITICAL), 4)
            rec[f"{scope}_tier"] = tier(vals)
            rec[f"{scope}_blocking"] = "; ".join(k for k in CRITICAL if vals[k] < 1)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df = df.join(cls[["role", "bio_payload_capable", "specimen_habitat", "n_osd_studies", "splash_status",
                      "splash_category", "first_launch"]], on="entity_id")
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / "T3_sufficiency_scores.csv", index=False)
    pd.DataFrame(ev).to_csv(TABLES / "T3b_sufficiency_evidence.csv", index=False)
    items = pd.DataFrame([{"key": i.key, "label": i.label, "group": i.group, "critical": i.critical}
                          for i in ITEMS])
    items.to_csv(TABLES / "T3a_checklist_items.csv", index=False)
    return df


if __name__ == "__main__":
    d = run()
    h = d[d.specimen_habitat]
    print(f"{len(d)} entities; {len(h)} specimen habitats")
    print("public tiers (habitats):", h.public_tier.value_counts().to_dict())
    print("splash tiers (habitats):", h.splash_tier.value_counts().to_dict())
    print(h[[f"public_{i.key}" for i in ITEMS]].mean().round(2).to_string())
