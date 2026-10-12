"""Stage 1 - snapshot the three public NASA hardware sources.

Sources (no authentication; no personal data sent in headers):
  A. SPLASH instrument catalogue  visualization.osdr.nasa.gov/splash-api/public
  B. OSDR hardware registry        osdr.nasa.gov/geode-py/ws/api/{hardware,payload}
  C. OSDR study metadata           visualization.osdr.nasa.gov/biodata/api/v2

Everything is written verbatim to data/raw/<YYYY-MM-DD>/ with SHA256SUMS.
Later stages read only the snapshot.

    python -m hwreview.fetch [--date YYYY-MM-DD] [--skip-datasets]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from .paths import RAW

UA = "Hardware_OSDR_review/0.1 (space-biology hardware meta-analysis; github.com/dr-richard-barker)"
SPLASH = "https://visualization.osdr.nasa.gov/splash-api/public"
GEODE = "https://osdr.nasa.gov/geode-py/ws/api"
BIODATA = "https://visualization.osdr.nasa.gov/biodata/api/v2"
PAUSE = 0.15

DATASET_QUERY = (
    BIODATA
    + "/query/datasets/?investigation.study.comment.experiment%20platform"
    + "&investigation.study.comment.project%20identifier"
    + "&study.characteristics.organism&format=json.records"
)

_session = requests.Session()
_session.headers["User-Agent"] = UA


def get_json(url: str, timeout: float = 180, tries: int = 5):
    """GET JSON with polite pacing and exponential back-off on 429/5xx."""
    delay = 2.0
    for attempt in range(tries):
        time.sleep(PAUSE)
        try:
            r = _session.get(url, timeout=timeout)
        except requests.RequestException as e:
            err = repr(e)
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            err = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{url}: {err}")
        print(f"  retry {attempt + 1}/{tries} {url}: {err}", file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"{url}: gave up after {tries} tries")


def dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def fetch_splash(out: Path) -> None:
    print("SPLASH instruments")
    dump(get_json(f"{SPLASH}/instruments"), out / "splash" / "instruments.json")
    dump(get_json(f"{SPLASH}/instrumentsHeader"), out / "splash" / "instrumentsHeader.json")
    dump(get_json(f"{SPLASH}/instrumentFilterOptions"), out / "splash" / "instrumentFilterOptions.json")


def fetch_registry(out: Path) -> None:
    print("OSDR hardware registry")
    index = get_json(f"{GEODE}/hardware")
    dump(index, out / "registry" / "hardware_index.json")
    records, payload_urls, experiment_urls = {}, set(), set()
    for i, row in enumerate(index["data"]):
        url = row["hardware"]
        hid = url.rstrip("/").rsplit("/", 1)[-1]
        rec = get_json(url)
        records[hid] = rec
        parents = (rec or {}).get("parents") or {}
        payload_urls |= {p["payload"] for p in parents.get("payload") or [] if p.get("payload")}
        experiment_urls |= {e["experiment"] for e in parents.get("experiment") or [] if e.get("experiment")}
        if i % 25 == 0:
            print(f"  hardware {i + 1}/{len(index['data'])}")
    dump(records, out / "registry" / "hardware.json")
    for kind, urls in (("payload", payload_urls), ("experiment", experiment_urls)):
        recs = {}
        for i, url in enumerate(sorted(urls)):
            key = url.rstrip("/").rsplit("/", 1)[-1]
            try:
                recs[key] = get_json(url)
            except RuntimeError as e:  # e.g. 403 on malformed IDs in the registry
                recs[key] = {"_fetch_error": str(e)}
            if i % 25 == 0:
                print(f"  {kind} {i + 1}/{len(urls)}")
        dump(recs, out / "registry" / f"{kind}.json")


def fetch_studies(out: Path, per_dataset: bool = True) -> None:
    print("OSDR study platform query (slow)")
    rows = get_json(DATASET_QUERY, timeout=600)
    dump(rows, out / "biodata" / "datasets_platform.json")
    if not per_dataset:
        return
    ids = sorted({r.get("id.accession") or r.get("accession") for r in rows} - {None},
                 key=lambda s: int(s.split("-")[1]) if s.split("-")[-1].isdigit() else 0)
    meta = {}
    for i, acc in enumerate(ids):
        d = get_json(f"{BIODATA}/dataset/{acc}/", timeout=180)
        meta[acc] = (d or {}).get(acc, {}).get("metadata") if d else None
        if i % 50 == 0:
            print(f"  dataset {i + 1}/{len(ids)}")
    dump(meta, out / "biodata" / "dataset_metadata.json")


def write_checksums(out: Path) -> None:
    lines = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name not in ("SHA256SUMS", "FETCH_INFO.json"):
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--skip-datasets", action="store_true", help="skip per-dataset metadata")
    ap.add_argument("--only", choices=["splash", "registry", "studies"])
    a = ap.parse_args(argv)
    out = RAW / a.date
    out.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if a.only in (None, "splash"):
        fetch_splash(out)
    if a.only in (None, "registry"):
        fetch_registry(out)
    if a.only in (None, "studies"):
        fetch_studies(out, per_dataset=not a.skip_datasets)
    dump({"started_utc": started,
          "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "user_agent": UA,
          "sources": {"splash": SPLASH, "registry": GEODE, "biodata": BIODATA}},
         out / "FETCH_INFO.json")
    write_checksums(out)
    print(f"snapshot written to {out}")


if __name__ == "__main__":
    main()
