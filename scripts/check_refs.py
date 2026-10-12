#!/usr/bin/env python3
"""Check every DOI in latex/references.bib against Crossref.

Fails (exit 1) when a DOI does not resolve, or when the title, year, volume or first
author's family name disagrees with Crossref. No personal data is sent: the
User-Agent names the project only. Entries whose authors Crossref does not list are
reported so they can be checked against the publisher page by hand
(record the check in latex/REFERENCE_CHECKS.md).
"""
from __future__ import annotations

import difflib
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

BIB = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "latex" / "references.bib"
UA = "Hardware_OSDR_review/0.1 (reference check; github.com/dr-richard-barker)"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", re.sub(r"[{}\\'`^\"~]", "", s or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split())


def entries(text: str):
    """Brace-matching BibTeX reader: yields (key, {field: value})."""
    i = 0
    while True:
        i = text.find("@", i)
        if i < 0:
            return
        j = text.index("{", i)
        depth, k = 0, j
        while True:
            depth += (text[k] == "{") - (text[k] == "}")
            if depth == 0:
                break
            k += 1
        body = text[j + 1:k]
        key, rest = body.split(",", 1)
        fields, pos = {}, 0
        for m in re.finditer(r"(\w+)\s*=\s*\{", rest):
            if m.start() < pos:
                continue
            d, q = 1, m.end()
            while d:
                d += (rest[q] == "{") - (rest[q] == "}")
                q += 1
            fields[m.group(1).lower()] = rest[m.end():q - 1].strip()
            pos = q
        yield key.strip(), fields
        i = k


def main() -> int:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    bad, warn = [], []
    n_seen = 0
    for key, f in entries(BIB.read_text()):
        n_seen += 1
        doi = f.get("doi")
        if not doi:
            continue
        for attempt in range(4):
            r = s.get(f"https://api.crossref.org/works/{doi}", timeout=60)
            if r.status_code != 429:
                break
            time.sleep(2 ** (attempt + 1))
        if r.status_code != 200:
            bad.append(f"{key}: DOI {doi} -> HTTP {r.status_code}")
            continue
        m = r.json()["message"]
        title = (m.get("title") or [""])[0]
        if difflib.SequenceMatcher(None, norm(title), norm(f.get("title", ""))).ratio() < 0.85:
            bad.append(f"{key}: title mismatch\n   bib:      {f.get('title')}\n   crossref: {title}")
        years = {(m.get(k) or {}).get("date-parts", [[None]])[0][0] for k in ("published-print", "published-online", "issued")}
        if f.get("year") and int(f["year"]) not in years:
            bad.append(f"{key}: year {f['year']} not in Crossref {sorted(y for y in years if y)}")
        if f.get("volume") and m.get("volume") and f["volume"] != m["volume"]:
            bad.append(f"{key}: volume {f['volume']} vs Crossref {m['volume']}")
        au = m.get("author") or []
        if au:
            first_bib = re.split(r"\s+and\s+", f.get("author", ""))[0]
            fam = au[0].get("family", "")
            if not set(norm(fam).split()) <= set(norm(first_bib).split()):
                bad.append(f"{key}: first author '{first_bib}' vs Crossref '{fam}'")
        else:
            warn.append(f"{key}: Crossref lists no authors; check against the publisher page")
        time.sleep(0.4)
    for w in warn:
        print("WARN", w)
    for b in bad:
        print("FAIL", b)
    if n_seen == 0:
        bad.append("no BibTeX entries parsed - the checker would be vacuous")
    print(f"{'FAILED' if bad else 'OK'}: {n_seen} entries, {len(bad)} problem(s), {len(warn)} warning(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
