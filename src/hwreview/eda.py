"""OSDR Environmental Data App (EDA): snapshot and quality control of ISS-cabin telemetry.

EDA (https://visualization.osdr.nasa.gov/eda/) serves temperature, relative humidity and CO2 for
Rodent Research and plant missions, flight ("iss") and ground control ("ground"), plus daily
absorbed dose. In EDA's own words the measurements were "recorded in the ISS cabin and ground
control for the duration of the mission": they describe the air around the hardware, not its
interior.

    python -m hwreview.eda            # snapshot into data/raw/<SNAPSHOT>/eda/ (network)

Every response is stored verbatim (gzip, mtime 0) with its own SHA256SUMS and FETCH_INFO.json, so
the main snapshot's checksums are untouched. Later stages read only the snapshot.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .fetch import UA
from .paths import snapshot_dir

API = "https://visualization.osdr.nasa.gov/eda/api"
PAGE = "https://visualization.osdr.nasa.gov/eda/"
LOCATION_QUOTE = ("On the Mission Dashboard the users can visualize temperature, carbon dioxide (CO2), and relative "
                  "humidity measurements and radiation doses recorded in the ISS cabin and ground control for the "
                  "duration of the mission.")
PAUSE = 0.3
VARS = ("temperature", "humidity", "co2")
# physically possible cabin values; anything outside is a logging artefact
BOUNDS = {"temperature": (5.0, 40.0), "humidity": (1.0, 100.0), "co2": (100.0, 20000.0)}
# a CO2 reading held unchanged for this long is a fill value, not a measurement (a live cabin
# CO2 signal at 1 ppm resolution changes within minutes)
HELD_CO2 = pd.Timedelta(hours=2)


def eda_dir() -> Path:
    return snapshot_dir() / "eda"


# ---------------------------------------------------------------- fetch
def _get(session: requests.Session, url: str, tries: int = 5) -> tuple[int, bytes]:
    delay = 2.0
    for _ in range(tries):
        time.sleep(PAUSE)
        try:
            r = session.get(url, timeout=300)
        except requests.RequestException:
            status, body = -1, b""
        else:
            status, body = r.status_code, r.content
            if status not in (429, 500, 502, 503, 504):
                return status, body
        time.sleep(delay)
        delay *= 2
    return status, body


def _write_gz(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(body)


def fetch() -> Path:
    out = eda_dir()
    s = requests.Session()
    s.headers["User-Agent"] = UA                      # no personal data in any header
    info = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "api": API,
            "user_agent": UA, "responses": {}}
    status, body = _get(s, f"{API}/missions/")
    if status != 200:
        raise RuntimeError(f"EDA missions list: HTTP {status}")
    _write_gz(out / "missions.json.gz", body)
    info["responses"]["missions"] = status
    for m in json.loads(body):
        name = m["name"]
        for kind, path in (("telemetry", "telemetry_data"), ("radiation", "radiation_data")):
            status, body = _get(s, f"{API}/missions/{name}/{path}/")
            info["responses"][f"{name}/{kind}"] = status
            if status == 200:
                _write_gz(out / kind / f"{name}.json.gz", body)
    info["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (out / "FETCH_INFO.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}"
             for p in sorted(out.rglob("*.json.gz"))]
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return out


# ---------------------------------------------------------------- load + QC
def _read(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def missions() -> pd.DataFrame:
    return pd.DataFrame(_read(eda_dir() / "missions.json.gz"))


def verify_checksums() -> None:
    d = eda_dir()
    for ln in (d / "SHA256SUMS").read_text().splitlines():
        h, rel = ln.split("  ", 1)
        if hashlib.sha256((d / rel).read_bytes()).hexdigest() != h:
            raise RuntimeError(f"EDA snapshot checksum mismatch: {rel}")


def telemetry(mission: str, qc: bool = True) -> tuple[pd.DataFrame, dict]:
    """Telemetry with UTC times; with qc=True, duplicate timestamps merged, out-of-range values and
    held CO2 fills set to NaN. Returns (frame, qc counts)."""
    p = eda_dir() / "telemetry" / f"{mission}.json.gz"
    df = pd.DataFrame(_read(p))
    rep = {"rows_raw": len(df)}
    if df.empty:
        return df, rep
    df["time"] = pd.to_datetime(df["time"], utc=True)
    cols = [f"{v}_{s}" for v in VARS for s in ("iss", "ground") if f"{v}_{s}" in df]
    df = df[["time"] + cols].sort_values("time")
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    if not qc:
        return df.reset_index(drop=True), rep
    dup = int(df.time.duplicated().sum())
    df = df.groupby("time", as_index=False).first()          # first non-null value per column
    rep["duplicate_times"] = dup
    for c in cols:
        lo, hi = BOUNDS[c.rsplit("_", 1)[0]]
        bad = df[c].notna() & ~df[c].between(lo, hi)
        rep[f"{c}:out_of_range"] = int(bad.sum())
        df.loc[bad, c] = np.nan
        if c.startswith("co2_"):
            held = _held_mask(df.time, df[c])
            rep[f"{c}:held"] = int(held.sum())
            df.loc[held, c] = np.nan
    return df.reset_index(drop=True), rep


def _held_mask(t: pd.Series, x: pd.Series) -> pd.Series:
    """True where x stays exactly constant for at least HELD_CO2."""
    v = x.to_numpy()
    grp = np.cumsum(np.r_[True, ~((v[1:] == v[:-1]) & ~np.isnan(v[1:]))])
    g = pd.Series(grp, index=x.index)
    span = t.groupby(g).transform(lambda s: s.iloc[-1] - s.iloc[0])
    return (span >= HELD_CO2) & x.notna()


def radiation(mission: str) -> pd.DataFrame:
    p = eda_dir() / "radiation" / f"{mission}.json.gz"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(_read(p))
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


if __name__ == "__main__":
    o = fetch()
    print(o, sum(1 for _ in o.rglob("*.json.gz")), "files")
