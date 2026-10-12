"""Stage 2a - internal consistency of SPLASH records.

Inspection of the 2026-10-12 snapshot showed records whose descriptive
fields belong to a *different* instrument (e.g. "Plant Growth Unit" listing
"RNA from microbial cultures..." as its specimens). Before any field is used
for classification or scoring, this stage tests every record objectively:

1. Field attribution (TF-IDF). For each descriptive field F of record i,
   compute cosine similarity between F and the identity text
   (name + alternate names + background) of every record j. F is flagged
   'displaced' when it shares almost nothing with its own record
   (sim_i <= SIM_OWN_MAX) but matches a record within ADJ rows
   (|i - j| <= ADJ, sim_j >= SIM_MIN): the signature of a row-offset error.
2. Organism contradiction. Organism classes named in specimen_types_supported
   are compared with those named in the record's own name + background; a
   flag is raised when both are non-empty and disjoint.
3. Name/background mismatch. The record's name is compared with its own
   background; a flag is raised when the background names a different
   instrument (its best-matching name is another record's).

Outputs results/tables/T0_splash_consistency.csv (per record x field) and
the set of fields that downstream stages must treat as untrusted.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import pandas as pd

from . import sources
from .lexicon import ORG_RE, classes_in
from .paths import TABLES

FIELDS = ["specimen_types_supported", "specimen_size", "dims", "volume", "mass",
          "power", "flight_heritage", "lighting", "gas_control", "rh_range",
          "temperature_range", "measurements", "note_specs"]
# A row-offset error moves a value onto a neighbouring row. Flag a field when it
# shares (almost) nothing with its own record's identity text but clearly matches
# a record within ADJ rows of it. Calibrated on hand-checked cases listed in
# tests/test_consistency.py; generic values that merely resemble a distant record
# (e.g. BRIC and Spectrum both "plant, microbes, fungi, worms") are not flagged.
SIM_OWN_MAX = 0.05
SIM_MIN = 0.14
ADJ = 3
STOP = set("""a an the and or of for to in on with by as at from is are be this that it its
into within each up per can may such via using used use other others any all also than""".split())
TOK = re.compile(r"[a-z][a-z0-9]+")


def tokens(s: str) -> list[str]:
    return [t for t in TOK.findall((s or "").lower()) if t not in STOP and len(t) > 2]


def tfidf_matrix(docs: list[list[str]], vocab_docs: list[list[str]]):
    df = Counter(t for d in vocab_docs for t in set(d))
    n = len(vocab_docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    vocab = {t: k for k, t in enumerate(sorted(idf))}
    M = np.zeros((len(docs), len(vocab)))
    for i, d in enumerate(docs):
        for t, c in Counter(d).items():
            if t in vocab:
                M[i, vocab[t]] = (1 + math.log(c)) * idf[t]
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    return M / np.where(norms == 0, 1, norms)


def identity_text(r: pd.Series) -> str:
    alt = r.get("alternate_names")
    alt = " ".join(alt) if isinstance(alt, list) else (alt or "")
    return f"{r['name']} {alt} {r.get('background') or ''}"


def run() -> pd.DataFrame:
    sp = sources.splash()
    ids = list(sp.index)
    ident_docs = [tokens(identity_text(sp.loc[i])) for i in ids]
    ident = tfidf_matrix(ident_docs, ident_docs)
    name_docs = [tokens(sp.loc[i, "name"] + " " + " ".join(sp.loc[i, "alternate_names"] or [])
                        if isinstance(sp.loc[i, "alternate_names"], list) else sp.loc[i, "name"])
                 for i in ids]
    rows = []
    for f in FIELDS:
        vals = [sp.loc[i].get(f) for i in ids]
        docs = [tokens(str(v)) if sources.is_informative(v) else [] for v in vals]
        V = tfidf_matrix(docs, ident_docs)
        S = V @ ident.T
        for k, i in enumerate(ids):
            if len(docs[k]) < 3:  # too short to attribute ("Middeck Locker", "Y", "1 atm")
                continue
            own = S[k, k]
            S_other = S[k].copy()
            S_other[k] = -1
            j = int(np.argmax(S_other))
            near = [m for m in range(len(ids)) if m != k and abs(ids[m] - i) <= ADJ]
            jn = max(near, key=lambda m: S[k, m]) if near else j
            flag = own <= SIM_OWN_MAX and S[k, jn] >= SIM_MIN and S[k, jn] >= S_other[j] - 1e-9
            if flag:
                j = jn
            rows.append({"splash_id": i, "name": sp.loc[i, "name"], "check": "field_attribution",
                         "field": f, "value": str(vals[k])[:160], "sim_own": round(float(own), 3),
                         "best_other_id": ids[j], "best_other_name": sp.loc[ids[j], "name"],
                         "sim_best_other": round(float(S_other[j]), 3), "flag": bool(flag)})
    # organism contradiction
    for i in ids:
        r = sp.loc[i]
        st = r.get("specimen_types_supported")
        if not sources.is_informative(st):
            continue
        a = classes_in(str(st), ORG_RE)
        b = classes_in(f"{r['name']} {r.get('background') or ''}", ORG_RE)
        if a and b:
            rows.append({"splash_id": i, "name": r["name"], "check": "organism_contradiction",
                         "field": "specimen_types_supported", "value": str(st)[:160],
                         "sim_own": None, "best_other_id": None, "best_other_name": None,
                         "sim_best_other": None,
                         "flag": not (a & b),
                         "detail": f"field={sorted(a)} identity={sorted(b)}"})
    # name vs own background
    bg_docs = [tokens(sp.loc[i].get("background") or "") for i in ids]
    B = tfidf_matrix(bg_docs, ident_docs)
    N = tfidf_matrix(name_docs, ident_docs)
    S = B @ N.T
    for k, i in enumerate(ids):
        if len(bg_docs[k]) < 5:
            continue
        own = S[k, k]
        S_other = S[k].copy()
        S_other[k] = -1
        j = int(np.argmax(S_other))
        rows.append({"splash_id": i, "name": sp.loc[i, "name"], "check": "name_background",
                     "field": "background", "value": str(sp.loc[i].get("background"))[:160],
                     "sim_own": round(float(own), 3), "best_other_id": ids[j],
                     "best_other_name": sp.loc[ids[j], "name"],
                     "sim_best_other": round(float(S_other[j]), 3),
                     "flag": bool(S_other[j] >= 0.2 and S_other[j] - own >= 0.15)})
    out = pd.DataFrame(rows)
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(TABLES / "T0_splash_consistency.csv", index=False)
    return out


def untrusted_fields() -> set[tuple[int, str]]:
    """(splash_id, field) pairs flagged by any check; downstream treats these as missing."""
    p = TABLES / "T0_splash_consistency.csv"
    df = pd.read_csv(p) if p.exists() else run()
    df = df[df["flag"]]
    out = set(zip(df["splash_id"].astype(int), df["field"]))
    # a record whose background describes another instrument: its free text cannot anchor it
    return out


if __name__ == "__main__":
    t = run()
    f = t[t["flag"]]
    print(f"{len(t)} checks, {len(f)} flags across {f['splash_id'].nunique()} records")
    print(f.groupby("check").size())
    with pd.option_context("display.width", 250, "display.max_colwidth", 60, "display.max_rows", 200):
        print(f[["splash_id", "name", "check", "field", "value", "sim_own", "best_other_id",
                 "best_other_name", "sim_best_other"]].to_string(index=False))
