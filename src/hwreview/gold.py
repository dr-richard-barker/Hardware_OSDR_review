"""Validate the automated MI-CFD-HW scorer against blind human-style ratings.

Two raters scored a seeded random sample of 12 specimen-housing entities
(data/curated/gold/sample.csv; seed 20261012) from the raw source text only,
blind to the automated scores and to each other. This module reports

* inter-rater agreement (exact agreement, linearly weighted Cohen's kappa),
* the adjudicated gold standard (agreements kept; disagreements resolved in
  data/curated/gold/adjudication.csv with a written reason),
* automated-vs-gold agreement, per item and overall, plus presence/absence
  precision and recall (score >= 0.5 counted as 'present').
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .paths import CURATED, TABLES
import re

from .evidence import Text
from .sufficiency import ITEMS, score_texts

GOLD = CURATED / "gold"
LEVELS = [0.0, 0.5, 1.0]


def weighted_kappa(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    k = len(LEVELS)
    idx = {v: i for i, v in enumerate(LEVELS)}
    O = np.zeros((k, k))
    for x, y in zip(a, b):
        O[idx[x], idx[y]] += 1
    O /= O.sum()
    E = np.outer(O.sum(1), O.sum(0))
    W = np.array([[abs(i - j) / (k - 1) for j in range(k)] for i in range(k)])
    return float(1 - (W * O).sum() / (W * E).sum())


def load_raters() -> pd.DataFrame:
    a = pd.read_csv(GOLD / "rater_A.csv")
    b = pd.read_csv(GOLD / "rater_B.csv")
    m = a.merge(b, on=["entity_id", "item"], suffixes=("_A", "_B"))
    assert len(m) == len(a) == len(b), "rater files do not align"
    return m


def gold_standard() -> pd.DataFrame:
    m = load_raters()
    adj_p = GOLD / "adjudication.csv"
    adj = pd.read_csv(adj_p) if adj_p.exists() else pd.DataFrame(columns=["entity_id", "item", "score", "reason"])
    m = m.merge(adj[["entity_id", "item", "score", "reason"]].rename(columns={"score": "score_adj"}),
                on=["entity_id", "item"], how="left")
    agree = m.score_A == m.score_B
    m["gold"] = np.where(agree, m.score_A, m.score_adj)
    missing = m[~agree & m.score_adj.isna()]
    if len(missing):
        raise ValueError(f"{len(missing)} disagreements lack an adjudication: "
                         + ", ".join(missing.entity_id + ":" + missing.item))
    return m


UNIT = re.compile(r"^--- unit (\d+) \| source=(\S+) record=(\S+) field=(.*)$", re.M)


def frozen_texts(entity_id: str) -> list[Text]:
    """Re-read the exact text units the raters saw (data/curated/gold/texts/<id>.txt)."""
    raw = (GOLD / "texts" / f"{entity_id}.txt").read_text()
    heads = list(UNIT.finditer(raw))
    out = []
    for k, h in enumerate(heads):
        end = heads[k + 1].start() if k + 1 < len(heads) else len(raw)
        out.append(Text(h.group(2), h.group(3), h.group(4).strip(), "", raw[h.end():end].strip()))
    return out


def run():
    m = load_raters()
    out = {"n_cells": len(m), "n_entities": m.entity_id.nunique(),
           "rater_exact_agreement": float((m.score_A == m.score_B).mean()),
           "rater_weighted_kappa": weighted_kappa(m.score_A, m.score_B),
           "rater_presence_agreement": float(((m.score_A >= .5) == (m.score_B >= .5)).mean())}
    g = gold_standard()
    # score the frozen texts the raters saw, so scorer and raters judge identical input
    auto = {e: {k: v["score"] for k, v in score_texts(frozen_texts(e)).items()} for e in g.entity_id.unique()}
    g["auto"] = [auto[e][i] for e, i in zip(g.entity_id, g["item"])]
    out["auto_exact_agreement"] = float((g.auto == g.gold).mean())
    out["auto_weighted_kappa"] = weighted_kappa(g.auto, g.gold)
    pres_auto, pres_gold = g.auto >= .5, g.gold >= .5
    tp = int((pres_auto & pres_gold).sum())
    out["auto_presence_precision"] = tp / max(1, int(pres_auto.sum()))
    out["auto_presence_recall"] = tp / max(1, int(pres_gold.sum()))
    ent = g.groupby("entity_id")[["gold", "auto"]].mean()
    out["entity_completeness_spearman"] = float(ent.gold.corr(ent.auto, method="spearman"))
    out["entity_completeness_mean_gold"] = float(ent.gold.mean())
    out["entity_completeness_mean_auto"] = float(ent.auto.mean())
    per_item = []
    for it in ITEMS:
        s = g[g["item"] == it.key]
        per_item.append({"item": it.key, "label": it.label,
                         "rater_agreement": float((s.score_A == s.score_B).mean()),
                         "auto_vs_gold_agreement": float((s.auto == s.gold).mean()),
                         "gold_mean": float(s.gold.mean()), "auto_mean": float(s.auto.mean())})
    pd.DataFrame(per_item).to_csv(TABLES / "T5_scorer_validation_items.csv", index=False)
    g.to_csv(TABLES / "T5b_gold_cells.csv", index=False)
    (TABLES / "T5_scorer_validation.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    import sys
    if "--raters" in sys.argv:
        m = load_raters()
        print("exact", (m.score_A == m.score_B).mean().round(3), "kappa_w", round(weighted_kappa(m.score_A, m.score_B), 3))
        d = m[m.score_A != m.score_B]
        print(len(d), "disagreements")
        pd.set_option("display.width", 250)
        pd.set_option("display.max_colwidth", 90)
        print(d[["entity_id", "item", "score_A", "quote_A", "score_B", "quote_B"]].to_string(index=False))
    else:
        print(json.dumps(run(), indent=1))
