"""Stage 2b - crosswalk SPLASH <-> OSDR registry <-> study 'experiment platform'.

The three sources share no identifier.

Step 1 - hardware entities are built from SPLASH (S<id>) and registry
(R<id>) nodes only, joined by
  * exact match of a normalised alias (name, ';'-separated parts, alternate
    names, the name without its parenthetical), or
  * an acronym that is unambiguous across both sources, or
  * a curated 'link' in data/curated/crosswalk_overrides.csv.
A join that would put two SPLASH records in one entity is refused unless
curated (SPLASH has deliberate near-duplicates, e.g. BRIC vs BRIC-PDFU).

Step 2 - every study platform string is split into components (top-level
commas / ' and '), and each component is *mapped* (many-to-many, never
merged) onto entities by exact alias, unambiguous acronym, or containment of
a specific (>= 2-token) alias. Exact and acronym matches beat containment;
among containments the longest alias wins. Curated mappings override.

Step 3 - components that map to nothing become platform-only entities,
grouped by identical core name or shared acronym.

Fuzzy matches are NEVER applied automatically; they go to
data/derived/crosswalk_proposals.csv for a human to accept or reject in the
overrides file.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

import pandas as pd

from . import sources
from .paths import CURATED, DERIVED

STOPWORDS = {"the", "a", "an", "of", "for", "and", "in", "system", "systems", "hardware", "facility",
             "unit", "units", "experiment", "module", "iss", "nasa", "esa", "jaxa", "flight"}
PAREN = re.compile(r"\(([^)]{2,60})\)")
ACRO = re.compile(r"\b([A-Z][A-Za-z]*[A-Z][A-Z0-9\-]*|[A-Z]{3,}[A-Z0-9\-]*)\b")
GENERIC_ACRONYMS = {"ISS", "NASA", "ESA", "JAXA", "KSC", "ARC", "JSC", "MSFC", "LED", "RNA", "DNA",
                    "USA", "STS", "EXPRESS", "ISIS", "SPX", "HTV", "EUE", "ECS", "GN2", "N/A", "CTB",
                    "HEPA", "BB-1F", "BB-2", "EU", "CO2", "UV", "RF", "PI"}


def norm(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[™®’']", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def core(s: str) -> str:
    return " ".join(t for t in norm(PAREN.sub("", s or "")).split() if t not in STOPWORDS)


def aliases(name: str, extra=()) -> tuple[set[str], set[str]]:
    """(normalised aliases, acronyms) for a display name."""
    names = {name, *extra}
    for part in re.split(r"\s*;\s*", name or ""):
        names |= {part, PAREN.sub("", part)}
    al, ac = set(), set()
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        al |= {norm(PAREN.sub("", n)), norm(n)}
        for p in PAREN.findall(n):
            p = p.strip()
            if re.fullmatch(r"[A-Za-z0-9\-/ ]{3,16}", p) and any(ch.isupper() for ch in p) and " " not in p:
                ac.add(p.upper())
        for m in ACRO.findall(PAREN.sub("", n)):
            if len(m) >= 3 and not m.isdigit() and sum(ch.isupper() for ch in m) >= 2:
                ac.add(m.upper())
    al.discard("")
    return al, {a for a in ac if a not in GENERIC_ACRONYMS}


def split_components(s: str) -> list[str]:
    """Split a platform string at top-level ',' / ' and ' (not inside parentheses)."""
    out, depth, buf = [], 0, ""
    i = 0
    while i < len(s):
        ch = s[i]
        depth += (ch == "(") - (ch == ")")
        if depth == 0 and ch == ",":
            out.append(buf)
            buf = ""
        elif depth == 0 and s[i:i + 5].lower() == " and " and not re.search(r"(spacelab|research|fluid)\s*$", buf, re.I):
            out.append(buf)
            buf = ""
            i += 4
        else:
            buf += ch
        i += 1
    out.append(buf)
    return [c.strip() for c in out if c.strip()]


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def load_overrides() -> pd.DataFrame:
    p = CURATED / "crosswalk_overrides.csv"
    if not p.exists():
        return pd.DataFrame(columns=["node_a", "node_b", "decision", "reason"])
    return pd.read_csv(p, comment="#").fillna("")


def hw_nodes() -> pd.DataFrame:
    rows = []
    for i, r in sources.splash().iterrows():
        alt = r.get("alternate_names") if isinstance(r.get("alternate_names"), list) else []
        al, ac = aliases(r["name"], alt)
        rows.append({"node": f"S{i}", "source": "splash", "name": r["name"], "aliases": al, "acronyms": ac})
    for hid, r in sources.registry().iterrows():
        al, ac = aliases(r["name"])
        rows.append({"node": f"R{hid}", "source": "registry", "name": r["name"], "aliases": al, "acronyms": ac})
    return pd.DataFrame(rows).set_index("node", drop=False)


def run(write: bool = True):
    nodes = hw_nodes()
    ov = load_overrides()
    curated_link = [(a, b, w) for a, b, d, w in ov[["node_a", "node_b", "decision", "reason"]].values if d == "link"]
    nolink = {frozenset((a, b)) for a, b, d in ov[["node_a", "node_b", "decision"]].values if d == "nolink"}
    dsu = DSU()
    members = defaultdict(set)
    for n in nodes.index:
        dsu.find(n)
        members[n] = {n}
    links, proposals = [], []

    def n_splash(root):
        return sum(1 for m in members[root] if m.startswith("S"))

    def join(a, b, method, key, force=False):
        ra, rb = dsu.find(a), dsu.find(b)
        if ra == rb or frozenset((a, b)) in nolink:
            return
        if not force and n_splash(ra) and n_splash(rb):
            proposals.append({"node_a": a, "name_a": nodes.loc[a, "name"], "node_b": b, "name_b": nodes.loc[b, "name"],
                              "basis": f"{method} '{key}' would merge two SPLASH records"})
            return
        dsu.union(a, b)
        r = dsu.find(a)
        members[r] = members.pop(ra, {ra}) | members.pop(rb, {rb})
        links.append({"node_a": a, "node_b": b, "method": method, "key": key})

    by_alias, by_acro = defaultdict(set), defaultdict(set)
    for n, r in nodes.iterrows():
        for a in r["aliases"]:
            if len(a) >= 4:
                by_alias[a].add(n)
        for a in r["acronyms"]:
            by_acro[a].add(n)
    for a, b, w in curated_link:
        if a[:1] in "SR" and b[:1] in "SR":
            join(a, b, "curated", w, force=True)
    for key, ns in sorted(by_alias.items()):
        ns = sorted(ns)
        for b in ns[1:]:
            join(ns[0], b, "exact_alias", key)
    for key, ns in sorted(by_acro.items()):
        per = defaultdict(list)
        for n in ns:
            per[nodes.loc[n, "source"]].append(n)
        if len(ns) >= 2 and all(len(v) == 1 for v in per.values()):
            ns = sorted(ns)
            for b in ns[1:]:
                join(ns[0], b, "acronym", key)
        elif len(ns) >= 2:
            ns = sorted(ns)
            for b in ns[1:]:
                if dsu.find(ns[0]) != dsu.find(b):
                    proposals.append({"node_a": ns[0], "name_a": nodes.loc[ns[0], "name"], "node_b": b,
                                      "name_b": nodes.loc[b, "name"], "basis": f"ambiguous acronym {key}"})

    # entity table for S/R
    groups = defaultdict(list)
    for n in nodes.index:
        groups[dsu.find(n)].append(n)
    ent_alias, ent_acro = defaultdict(set), defaultdict(set)
    for root, ms in groups.items():
        for m in ms:
            ent_alias[root] |= {a for a in nodes.loc[m, "aliases"] if len(a) >= 4}
            ent_acro[root] |= nodes.loc[m, "acronyms"]
    acro_owner = defaultdict(set)
    for root, acs in ent_acro.items():
        for a in acs:
            acro_owner[a].add(root)

    # step 2 - map platform components
    plat = sources.study_platforms()
    curated_map = defaultdict(set)
    curated_kind = {}
    for a, b, w in curated_link:
        if a.startswith("P:") and b[:1] in "SR":
            curated_map[a[2:]].add(dsu.find(b))
    for a, b, d, w in ov[["node_a", "node_b", "decision", "reason"]].values:
        if a.startswith("P:") and d.startswith("kind:"):
            curated_kind[a[2:]] = d.split(":", 1)[1]
    comp_rows = []
    for s in sorted(plat["platform"].dropna().unique()):
        for c in split_components(s):
            al, ac = aliases(c)
            hits, method = set(), None
            if c in curated_map or s in curated_map:
                hits, method = curated_map.get(c) or curated_map.get(s), "curated"
            elif c in curated_kind or s in curated_kind:
                hits, method = set(), "curated_kind"
            else:
                exact = {r for r, als in ent_alias.items() if al & als}
                acr = {r for a in ac for r in acro_owner.get(a, ()) if len(acro_owner[a]) == 1}
                if exact or acr:
                    hits, method = exact | acr, "exact_or_acronym"
                else:
                    best, best_len = set(), 0
                    for r, als in ent_alias.items():
                        for a in als:
                            if len(a.split()) < 2 or len(a) < 8:
                                continue
                            for x in al:
                                if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", x) or (
                                        len(x.split()) >= 2 and len(x) >= 8 and re.search(rf"(?<!\w){re.escape(x)}(?!\w)", a)):
                                    if len(a) > best_len:
                                        best, best_len = {r}, len(a)
                                    elif len(a) == best_len:
                                        best.add(r)
                    if best:
                        hits, method = best, "containment"
            comp_rows.append({"platform_string": s, "component": c, "entity_roots": sorted(hits),
                              "method": method, "kind": curated_kind.get(c) or curated_kind.get(s),
                              "aliases": al, "acronyms": ac})
    comps = pd.DataFrame(comp_rows)

    # step 3 - platform-only entities from unmapped components
    unm = comps[(comps["entity_roots"].map(len) == 0)]
    pd_dsu = DSU()
    keys = list(unm.index)
    for k in keys:
        pd_dsu.find(k)
    for i, k in enumerate(keys):
        for k2 in keys[i + 1:]:
            a, b = unm.loc[k], unm.loc[k2]
            if core(a.component) == core(b.component) or (a.acronyms & b.acronyms):
                pd_dsu.union(k, k2)
    for k in keys:
        root = f"PX{pd_dsu.find(k)}"
        comps.at[k, "entity_roots"] = [root]
    # fuzzy proposals for unmapped components against hardware entities
    for k in keys:
        c = comps.loc[k, "component"]
        cc = core(c)
        if not cc:
            continue
        for root, ms in groups.items():
            nm = nodes.loc[ms[0], "name"]
            for m in ms:
                r = difflib.SequenceMatcher(None, cc, core(nodes.loc[m, "name"])).ratio()
                if r >= 0.8:
                    proposals.append({"node_a": f"P:{c}", "name_a": c, "node_b": m,
                                      "name_b": nodes.loc[m, "name"], "basis": f"fuzzy {r:.2f}"})
                    break

    # assemble entity table
    ents = {}
    for root, ms in groups.items():
        s_ids = sorted(int(m[1:]) for m in ms if m.startswith("S"))
        r_ids = sorted((m[1:] for m in ms if m.startswith("R")), key=lambda x: int(x) if x.isdigit() else 0)
        canon = nodes.loc[f"S{s_ids[0]}", "name"] if s_ids else nodes.loc[f"R{r_ids[0]}", "name"]
        ents[root] = {"canonical_name": canon.strip(), "splash_ids": s_ids, "registry_ids": r_ids,
                      "platform_strings": set(), "platform_components": set(), "kind": "hardware"}
    for _, r in comps.iterrows():
        for root in r["entity_roots"]:
            if root not in ents:
                ents[root] = {"canonical_name": r["component"], "splash_ids": [], "registry_ids": [],
                              "platform_strings": set(), "platform_components": set(),
                              "kind": r["kind"] or "hardware"}
            ents[root]["platform_strings"].add(r["platform_string"])
            ents[root]["platform_components"].add(r["component"])
    rows = []
    for root, e in ents.items():
        e = dict(e)
        e["platform_strings"] = sorted(e["platform_strings"])
        e["platform_components"] = sorted(e["platform_components"])
        k = ((0, e["splash_ids"][0], "") if e["splash_ids"] else
             (1, int(e["registry_ids"][0]) if e["registry_ids"][0].isdigit() else 0, "") if e["registry_ids"] else
             (2, 0, e["canonical_name"].lower()))
        rows.append({**e, "_k": k})
    df = pd.DataFrame(rows).sort_values("_k").drop(columns="_k").reset_index(drop=True)
    df.insert(0, "entity_id", [f"HW{k:03d}" for k in range(1, len(df) + 1)])
    df["n_nodes"] = df.splash_ids.map(len) + df.registry_ids.map(len) + df.platform_components.map(len)
    comps_out = comps.drop(columns=["aliases", "acronyms"]).copy()
    root_to_id = {}
    for root, e in ents.items():
        hit = df[(df.canonical_name == e["canonical_name"]) & (df.splash_ids.map(tuple) == tuple(e["splash_ids"]))
                 & (df.registry_ids.map(tuple) == tuple(e["registry_ids"]))]
        root_to_id[root] = hit.entity_id.iloc[0]
    comps_out["entity_ids"] = comps_out["entity_roots"].map(lambda rs: [root_to_id[r] for r in rs])
    comps_out = comps_out.drop(columns="entity_roots")
    if write:
        DERIVED.mkdir(parents=True, exist_ok=True)
        df.to_json(DERIVED / "entities.json", orient="records", indent=1)
        pd.DataFrame(links).to_csv(DERIVED / "crosswalk_links.csv", index=False)
        comps_out.to_json(DERIVED / "platform_components.json", orient="records", indent=1)
        pd.DataFrame(proposals).drop_duplicates().to_csv(DERIVED / "crosswalk_proposals.csv", index=False)
    return df, pd.DataFrame(links), comps_out, pd.DataFrame(proposals)


def load_entities() -> pd.DataFrame:
    df = pd.read_json(DERIVED / "entities.json", orient="records", dtype={"registry_ids": object})
    df["registry_ids"] = df["registry_ids"].map(lambda v: [str(x) for x in v])
    return df


if __name__ == "__main__":
    e, l, c, p = run()
    print(f"{len(e)} entities ({(e.splash_ids.map(len) + e.registry_ids.map(len) == 0).sum()} platform-only); "
          f"{len(l)} S/R links; {len(c)} platform components; {len(p)} proposals")
    print(l["method"].value_counts().to_string())
    print(c["method"].value_counts(dropna=False).to_string())
