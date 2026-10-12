"""ISS-cabin telemetry from the EDA snapshot: cabin conditions for the CFD exterior, and the
flight-minus-ground environmental offsets of the Rodent Research missions.

  T11a_cabin_rr1.csv           RR-1 cabin statistics (flight and ground columns, raw and quality
                               controlled) - the source of hardware/_iss_cabin.yaml
  T11_flight_ground.csv        per mission and variable: medians, flight - ground offset after
                               aligning the ground series by its best lag, spread, daily dose
  F9_flight_ground_offsets     the offsets, per mission

Windows are the on-orbit habitation periods in data/curated/eda_mission_windows.csv (chosen by hand
from EDA's milestones). EDA describes these as cabin measurements; none is inside any hardware.

    python -m hwreview.telemetry
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import eda, style
from .paths import CURATED, FIGURES, TABLES
from .style import plt

VARS = {"temperature": ("T", "°C"), "humidity": ("RH", "%"), "co2": ("CO$_2$", "ppm")}
CHOI_WINDOW = ("2014-09-25T00:00:00Z", "2014-11-01T00:00:00Z")   # Choi et al. 2020, "Sept 25 - Oct 31, 2014"
MAX_LAG_H = 168


def windows() -> pd.DataFrame:
    w = pd.read_csv(CURATED / "eda_mission_windows.csv")
    w["start_utc"] = pd.to_datetime(w.start_utc, utc=True)
    w["end_utc"] = pd.to_datetime(w.end_utc, utc=True)
    return w.set_index("mission")


def _stats(x: pd.Series) -> dict:
    x = x.dropna()
    if x.empty:
        return {"n": 0}
    return {"n": int(x.size), "min": float(x.min()), "p01": float(x.quantile(0.01)), "median": float(x.median()),
            "p99": float(x.quantile(0.99)), "max": float(x.max())}


def cabin_rr1(write: bool = True) -> pd.DataFrame:
    """RR-1 cabin statistics: the raw series over Choi et al.'s window (to compare with their quoted
    ranges) and the quality-controlled series over the RR-1 habitation window (used by the models)."""
    raw, _ = eda.telemetry("RR-1", qc=False)
    qc, _ = eda.telemetry("RR-1")
    w = windows().loc["RR-1"]
    rows = []
    for v in VARS:
        for col in ("iss", "ground"):
            c = f"{v}_{col}"
            a, b = pd.Timestamp(CHOI_WINDOW[0]), pd.Timestamp(CHOI_WINDOW[1])
            rows.append({"variable": v, "column": col, "window": "Choi 2020 (raw)",
                         **_stats(raw.loc[(raw.time >= a) & (raw.time < b), c])})
            rows.append({"variable": v, "column": col, "window": "RR-1 habitation (QC)",
                         **_stats(qc.loc[(qc.time >= w.start_utc) & (qc.time <= w.end_utc), c])})
    df = pd.DataFrame(rows)
    if write:
        df.to_csv(TABLES / "T11a_cabin_rr1.csv", index=False)
    return df


def _hourly(df: pd.DataFrame, col: str) -> pd.Series:
    return df.set_index("time")[col].resample("1h").mean()


def best_lag(iss: pd.Series, ground: pd.Series, t0, t1) -> tuple[int, float, float]:
    """Lag (h) of the ground series behind flight that minimises the median |flight - ground| of hourly
    means over the habitation window. Returns (lag, median |diff| at 0, at the best lag)."""
    f = iss[(iss.index >= t0) & (iss.index <= t1)]
    best, mad0 = (0, np.inf), np.nan
    for lag in range(-MAX_LAG_H, MAX_LAG_H + 1):
        g = ground.reindex(f.index + pd.Timedelta(hours=lag)).to_numpy()
        d = np.abs(f.to_numpy() - g)
        d = d[~np.isnan(d)]
        if d.size < 0.5 * f.notna().sum():          # require half the window to overlap
            continue
        m = float(np.median(d))
        if lag == 0:
            mad0 = m
        if m < best[1] - 1e-12 or (abs(m - best[1]) <= 1e-12 and abs(lag) < abs(best[0])):
            best = (lag, m)
    return best[0], mad0, best[1]


def flight_ground() -> pd.DataFrame:
    rows = []
    for m, w in windows().iterrows():
        df, qcrep = eda.telemetry(m)
        if df.empty:
            continue
        rad = eda.radiation(m)
        dose = rad.loc[(rad.time >= w.start_utc.floor("D")) & (rad.time <= w.end_utc), "total"] if len(rad) else []
        # one lag per mission, from CO2 when both columns exist (the most variable signal), else temperature
        lag_var = next((v for v in ("co2", "temperature") if df.get(f"{v}_iss") is not None
                        and df[f"{v}_iss"].notna().any() and df.get(f"{v}_ground") is not None
                        and df[f"{v}_ground"].notna().any()), None)
        if lag_var:
            lag, mad0, madb = best_lag(_hourly(df, f"{lag_var}_iss"), _hourly(df, f"{lag_var}_ground"),
                                       w.start_utc, w.end_utc)
        else:
            lag, mad0, madb = (np.nan,) * 3
        for v in VARS:
            ci, cg = f"{v}_iss", f"{v}_ground"
            if ci not in df or not df[ci].notna().any():
                continue
            fi = _hourly(df, ci)
            fi = fi[(fi.index >= w.start_utc) & (fi.index <= w.end_utc)]
            rec = {"mission": m, "variable": v, "window_start": w.start_utc.date(), "window_end": w.end_utc.date(),
                   "flight_median": float(fi.median()), "flight_hours": int(fi.notna().sum()),
                   "lag_variable": lag_var, "ground_lag_h": lag,
                   f"lag_median_abs_diff_at_0": mad0, "lag_median_abs_diff_at_best": madb,
                   "mean_daily_dose_mGy": float(np.mean(dose)) if len(dose) else np.nan,
                   "qc_held_or_out_of_range": int(sum(val for k, val in qcrep.items()
                                                      if k.startswith(v) and (k.endswith(":held")
                                                                              or k.endswith(":out_of_range"))))}
            if cg in df and df[cg].notna().any() and not np.isnan(lag):
                g = _hourly(df, cg).reindex(fi.index + pd.Timedelta(hours=int(lag)))
                d = fi.to_numpy() - g.to_numpy()
                d = d[~np.isnan(d)]
                rec.update({"ground_median": float(np.nanmedian(g.to_numpy())), "paired_hours": int(d.size),
                            "offset_median": float(np.median(d)), "offset_p25": float(np.percentile(d, 25)),
                            "offset_p75": float(np.percentile(d, 75))})
            rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "T11_flight_ground.csv", index=False)
    return df


def figure(t: pd.DataFrame):
    style.apply()
    t = t[t.offset_median.notna()]
    order = (windows().loc[t.mission.unique()].sort_values("start_utc").index.tolist())
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.4), sharey=True)
    y = {m: i for i, m in enumerate(order[::-1])}
    for ax, (v, (lab, unit)) in zip(axes, VARS.items()):
        s = t[t.variable == v]
        ax.axvline(0, color=style.MUTED, lw=0.8, zorder=1)
        for r in s.itertuples():
            ax.plot([r.offset_p25, r.offset_p75], [y[r.mission]] * 2, color=style.BLUE, alpha=0.35, lw=3,
                    solid_capstyle="round", zorder=2)
            ax.plot(r.offset_median, y[r.mission], "o", color=style.BLUE, ms=4.5, zorder=3)
        ax.set_title(f"Δ{lab} ({unit})", fontsize=8)
        ax.set_yticks(list(y.values()), list(y.keys()), fontsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax.grid(axis="x", alpha=0.3)
    h = [plt.Line2D([], [], marker="o", ls="", color=style.BLUE, label="median of hourly differences"),
         plt.Line2D([], [], color=style.BLUE, alpha=0.35, lw=3, label="interquartile range")]
    fig.legend(handles=h, loc="lower center", ncol=2, fontsize=7, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("ISS cabin (flight) minus ground control, hourly means during habitation", x=0.01, ha="left",
                 fontsize=8.5)
    fig.subplots_adjust(bottom=0.17, top=0.84, wspace=0.12)
    for ext in ("pdf", "png"):
        fig.savefig(FIGURES / f"F9_flight_ground_offsets.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)


def main():
    eda.verify_checksums()
    c = cabin_rr1()
    t = flight_ground()
    figure(t)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(c.to_string(index=False))
        print(t[["mission", "variable", "ground_lag_h", "flight_median", "ground_median", "offset_median",
                 "offset_p25", "offset_p75", "paired_hours", "mean_daily_dose_mGy"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
