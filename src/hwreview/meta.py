"""Stage 4b - meta-analysis: which hardware is documented well enough to model?

Inputs: T1 (classification) and T3 (MI-CFD-HW scores, 'public' scope).
Population: specimen-housing entities (live specimens housed in flight).

Analyses
  M1  completeness by hardware class, era, status, platform and source coverage
      (Kruskal-Wallis; pairwise Mann-Whitney U with Benjamini-Hochberg FDR)
  M2  completeness vs scientific use (Spearman rho with number of OSD studies)
  M3  usage x completeness quadrant (median splits) - the 'used but unmodellable' set
  M4  item-level missingness (share of entities scoring 0 / 0.5 / 1 on each item)
  M5  tier sensitivity: (a) as defined; (b) F2 waived when F1 evidence says
      sealed / passive; (c) any quantitative critical item counted at 0.5
  M6  catalogue-integrity defects found during curation (counts)

Outputs results/tables/T4_*.csv and results/tables/T4_summary.json
"""
from __future__ import annotations

import itertools
import json
import re

import numpy as np
import pandas as pd
from scipy import stats

from . import sources
from .paths import CURATED, DERIVED, TABLES
from .sufficiency import CRITICAL, ITEMS

CLASS_ORDER = ["plant", "rodent", "other_animal", "cell_microbe", "mixed"]


def hw_class(orgs: list[str]) -> str:
    """Dominant specimen class. Animals outrank plants, which outrank cells/microbes
    (cell/tissue/microbe mentions usually describe samples or co-culture)."""
    s = set(orgs) - {"human"}
    animal = s & {"rodent", "primate", "aquatic_vertebrate", "avian", "invertebrate"}
    if animal and "plant" in s:
        return "mixed"
    if animal == {"rodent"}:
        return "rodent"
    if animal:
        return "other_animal" if "rodent" not in animal else "mixed"
    if "plant" in s:
        return "plant"
    if s & {"cell_tissue", "microbe"}:
        return "cell_microbe"
    return "mixed"


def first_year(row, sp, pay_years) -> float:
    years = []
    for v in str(row["first_launch"]).split(";"):
        m = re.search(r"(19[5-9]\d|20[0-3]\d)", v)
        if m:
            years.append(int(m.group(1)))
    years += pay_years.get(row["entity_id"], [])
    return float(min(years)) if years else np.nan


def payload_years(cls: pd.DataFrame) -> dict:
    from .evidence import payload_info
    reg = sources.registry()
    out = {}
    for _, r in cls.iterrows():
        ys = []
        for rid in r["registry_ids"]:
            for pid in reg.loc[str(rid)]["payloads"]:
                for a, b in payload_info(pid)["mission_dates"]:
                    m = re.search(r"(19[5-9]\d|20[0-3]\d)", str(a or ""))
                    if m:
                        ys.append(int(m.group(1)))
        if ys:
            out[r["entity_id"]] = ys
    return out


def bh(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for k, i in enumerate(o[::-1]):
        rank = n - k
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return q


def group_test(df, col, value="public_completeness", min_n=3):
    d = df.dropna(subset=[col])
    groups = {k: g[value].values for k, g in d.groupby(col) if len(g) >= min_n}
    rows = [{"factor": col, "level": k, "n": len(v), "median": float(np.median(v)),
             "mean": float(np.mean(v)), "q1": float(np.quantile(v, .25)), "q3": float(np.quantile(v, .75))}
            for k, v in groups.items()]
    res = {"factor": col, "k": len(groups), "n": int(sum(len(v) for v in groups.values()))}
    if len(groups) >= 2:
        H, p = stats.kruskal(*groups.values())
        res.update({"H": float(H), "p": float(p),
                    "epsilon2": float((H - len(groups) + 1) / (res["n"] - len(groups)))})
        pairs = list(itertools.combinations(groups, 2))
        ps = [stats.mannwhitneyu(groups[a], groups[b], alternative="two-sided").pvalue for a, b in pairs]
        qs = bh(ps)
        res["pairwise"] = [{"a": a, "b": b, "p": float(p_), "q_BH": float(q_)}
                           for (a, b), p_, q_ in zip(pairs, ps, qs)]
    return rows, res


def f1_mode(quote: str | float) -> str:
    q = str(quote or "").lower()
    if re.search(r"sealed|hermetic|air[- ]?tight|closed (system|environment|container|canister)", q):
        return "sealed"
    if re.search(r"passive|breathable|membrane|vented|vents\b", q):
        return "passive"
    if re.search(r"fan|blower|forced|recirculat|air ?flow|ventilat|purg", q):
        return "forced"
    return "unknown"


def run():
    cls = pd.read_json(DERIVED / "classification.json")
    sc = pd.read_csv(TABLES / "T3_sufficiency_scores.csv")
    ev = pd.read_csv(TABLES / "T3b_sufficiency_evidence.csv")
    df = sc.merge(cls[["entity_id", "organism_classes_all", "platforms_from_missions", "splash_ids", "registry_ids",
                       "platform_strings"]], on="entity_id")
    df = df[df.specimen_habitat].copy()
    sp = sources.splash()
    py = payload_years(cls[cls.entity_id.isin(df.entity_id)])
    df["hw_class"] = df.organism_classes_all.map(hw_class)
    df["first_year"] = [first_year(r, sp, py) for _, r in df.iterrows()]
    df["era"] = pd.cut(df.first_year, [1950, 1980, 2000, 2010, 2030],
                       labels=["<1981", "1981-2000", "2001-2010", ">2010"], right=True).astype(object)
    df["status"] = df.splash_status.fillna("").map(lambda s: s.split(";")[0].strip() or "not in SPLASH")
    df["coverage"] = np.select([(df.splash_ids.map(len) > 0) & (df.registry_ids.map(len) > 0),
                                df.splash_ids.map(len) > 0, df.registry_ids.map(len) > 0],
                               ["SPLASH+registry", "SPLASH only", "registry only"], "study field only")

    def main_platform(d):
        if not d:
            return "no mission record"
        return max(d.items(), key=lambda kv: kv[1])[0]
    df["platform"] = df.platforms_from_missions.map(main_platform)
    df["used"] = df.n_osd_studies > 0

    group_rows, tests = [], []
    for col in ["hw_class", "era", "status", "platform", "coverage", "used"]:
        r, t = group_test(df.assign(used=df.used.map({True: "with OSD studies", False: "no OSD studies"})), col)
        group_rows += r
        tests.append(t)
    rho, p = stats.spearmanr(df.n_osd_studies, df.public_completeness)
    used = df[df.used]
    rho_u, p_u = stats.spearmanr(used.n_osd_studies, used.public_completeness) if len(used) > 3 else (np.nan, np.nan)

    # M3 quadrant on habitats with >=1 study
    med_c = df.public_completeness.median()
    q = used.assign(quadrant=np.where(used.public_completeness >= med_c, "documented", "under-documented"))
    q = q.sort_values(["n_osd_studies", "public_completeness"], ascending=[False, True])

    # M4 item missingness
    items = []
    for it in ITEMS:
        v = df[f"public_{it.key}"]
        items.append({"item": it.key, "label": it.label, "critical": it.critical,
                      "absent": float((v == 0).mean()), "qualitative": float((v == 0.5).mean()),
                      "quantitative": float((v == 1).mean()),
                      "splash_quantitative": float((df[f"splash_{it.key}"] == 1).mean())})

    # M5 tier sensitivity
    f1q = ev[ev["item"] == "F1"].set_index("entity_id")["quote"]
    df["f1_mode"] = df.entity_id.map(lambda e: f1_mode(f1q.get(e)))

    def tier_from(row, waive_f2=False, half_ok=False):
        s = {k: row[f"public_{k}"] for k in CRITICAL}
        if waive_f2 and row["f1_mode"] in ("sealed", "passive"):
            s["F2"] = 1.0
        thr = 0.5 if half_ok else 1.0
        if all(v >= thr for v in s.values()):
            return "A"
        return "B" if all(v >= 0.5 for v in s.values()) else "C"
    df["tier_waiveF2"] = df.apply(tier_from, axis=1, waive_f2=True)
    df["tier_lenient"] = df.apply(tier_from, axis=1, waive_f2=True, half_ok=True)
    sens = {c: df[c].value_counts().to_dict() for c in ["public_tier", "splash_tier", "tier_waiveF2", "tier_lenient"]}

    # M6 integrity defects
    rev = pd.read_csv(CURATED / "splash_field_review.csv")
    plat = sources.study_platforms()
    plat_ds = plat.groupby("osd")["platform"].apply(lambda x: x.notna().any())
    comps = pd.read_json(DERIVED / "platform_components.json")
    defects = {
        "splash_records": int(len(sp)),
        "splash_displaced_block": "121-147 (27 records)",
        "splash_field_verdicts": rev.verdict.value_counts().to_dict(),
        "splash_fields_all_empty": [f for f in ("study_links", "sources", "schematics", "related_tools")
                                    if not sp[f].map(sources.is_informative).any()],
        "osdr_datasets": int(plat_ds.size),
        "osdr_datasets_without_platform": int((~plat_ds).sum()),
        "distinct_platform_strings": int(plat.platform.nunique()),
        "platform_components_not_hardware": int(comps.kind.notna().sum()),
        "veggie_spellings": int(sum(1 for s in plat.platform.dropna().unique() if re.search(r"veggie", s, re.I))),
        "registry_catchall_payload": "Simulated_Environmental_Factors links a ground cabinet (registry 2052) to 36 studies",
        "splash_alias_conflict": "SPLASH #36 (MVP) lists 'MOBIAS' (a different bioreactor) as an alternate name",
    }

    TABLES.mkdir(parents=True, exist_ok=True)
    keep = ["entity_id", "canonical_name", "hw_class", "era", "first_year", "status", "platform", "coverage",
            "n_osd_studies", "public_completeness", "public_critical", "public_tier", "public_blocking",
            "splash_completeness", "splash_tier", "f1_mode", "tier_waiveF2", "tier_lenient"]
    df[keep].sort_values("public_completeness").to_csv(TABLES / "T4a_habitat_meta.csv", index=False)
    pd.DataFrame(group_rows).to_csv(TABLES / "T4b_group_completeness.csv", index=False)
    pd.DataFrame(items).to_csv(TABLES / "T4c_item_missingness.csv", index=False)
    q = df[df.used].assign(quadrant=np.where(df[df.used].public_completeness >= med_c, "documented",
                                             "under-documented"))
    q = q.sort_values(["n_osd_studies", "public_completeness"], ascending=[False, True])
    q[keep + ["quadrant"]].to_csv(TABLES / "T4d_usage_quadrant.csv", index=False)
    summary = {"n_habitats": int(len(df)), "n_used": int(df.used.sum()),
               "completeness_median_public": float(df.public_completeness.median()),
               "completeness_median_splash": float(df.splash_completeness.median()),
               "spearman_studies_completeness_all": {"rho": float(rho), "p": float(p)},
               "spearman_studies_completeness_used": {"rho": float(rho_u), "p": float(p_u)},
               "tests": tests, "tier_sensitivity": sens, "integrity_defects": defects,
               "under_documented_used": q[q.quadrant == "under-documented"].canonical_name.tolist()}
    (TABLES / "T4_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return df, summary


if __name__ == "__main__":
    d, s = run()
    print(json.dumps({k: v for k, v in s.items() if k != "tests"}, indent=1, default=str)[:3000])
    for t in s["tests"]:
        print(t["factor"], "k=", t["k"], "n=", t["n"], "H=", round(t.get("H", np.nan), 2), "p=", t.get("p"))
