"""Render manuscript and supplementary tables as LaTeX from the result CSVs (results/tex/*.tex).

No table in the manuscript is typed by hand: each is written here from a file a
pipeline stage produced.
"""
from __future__ import annotations

import math

import pandas as pd
import yaml

from .paths import CURATED, HARDWARE, ROOT, TABLES

OUT = ROOT / "results" / "tex"


def esc(s) -> str:
    s = "" if s is None or (isinstance(s, float) and s != s) else str(s)
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\^{}"),
                 ("µ", r"$\mu$"), ("μ", r"$\mu$"), ("°", r"$^\circ$"), ("±", r"$\pm$"), ("×", r"$\times$"),
                 ("–", "--"), ("—", "---"), ("≤", r"$\le$"), ("≥", r"$\ge$"), ("₂", r"$_2$"), ("′", "'"),
                 ("“", "``"), ("”", "''"), ("’", "'"), ("‑", "-"), ("≈", r"$\approx$"), ("²", r"$^2$"),
                 ("³", r"$^3$"), ("™", "")):
        s = s.replace(a, b)
    return s


def brk(s) -> str:
    """Escaped identifier that may break after underscores, dots and brackets."""
    t = esc(s)
    for a in ("\\_", ".", "]"):
        t = t.replace(a, a + "\\allowbreak{}")
    return t


def num(v, nd=2):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    if isinstance(v, (int,)) or (isinstance(v, float) and float(v).is_integer() and abs(v) >= 100):
        return f"{int(v):,}".replace(",", "{,}")
    v = float(v)
    if v != 0 and (abs(v) < 1e-2 or abs(v) >= 1e5):
        m, e = f"{v:.2e}".split("e")
        return f"${m}\\times10^{{{int(e)}}}$"
    return f"{v:.{nd}f}"


def tabular(df: pd.DataFrame, spec: str, header: list[str], caption: str, label: str, size=r"\footnotesize",
            long=False) -> str:
    lines = [f"\\begin{{table}}[htbp]\\centering{size}", f"\\caption{{{caption}}}\\label{{{label}}}",
             r"\begin{adjustbox}{max width=\linewidth}",
             f"\\begin{{tabular}}{{{spec}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    for _, r in df.iterrows():
        lines.append(" & ".join(str(x) for x in r.values) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}", r"\end{table}", ""]
    return "\n".join(lines)


def t_curated():
    d = pd.read_csv(TABLES / "T6_curated_tiers.csv").sort_values(["tier", "slug"])
    yes = lambda b: "\\checkmark" if b else "--"  # noqa: E731
    rows = pd.DataFrame({
        "hw": [esc(n.split(" (")[0])[:46] for n in d.name],
        "G1": d.G1.map(yes), "G2": d.G2.map(yes), "F1": d.F1.map(yes),
        "F2": [("n/a" if w else yes(f)) for f, w in zip(d.F2, d.F2_waived)], "E1": d.E1.map(yes),
        "B1": d.B1.map(yes), "tier": d.tier, "src": [f"{a}/{b}" for a, b in zip(d.n_sourced, d.n_parameters)]})
    return tabular(rows, "lcccccccr",
                   ["Hardware", "G1", "G2", "F1", "F2", "E1", "B1", "Tier", "sourced/params"],
                   "Critical MI-CFD-HW items after literature curation (\\checkmark sourced with a verbatim quotation; "
                   "F2 n/a: sealed or passive hardware). G1 enclosure dimensions; G2 specimen container; F1 ventilation "
                   "mode; F2 airflow; E1 temperature; B1 specimen.", "tab:curated", r"\scriptsize")


def t_verification():
    d = pd.read_csv(TABLES / "T8_verification_cavity.csv")
    rows = pd.DataFrame({
        "Ra": [f"$10^{{{int(round(math.log10(r)))}}}$" for r in d.Ra],
        "n64": d.Nu_64.map(lambda v: f"{v:.4f}"), "n96": d.Nu_96.map(lambda v: f"{v:.4f}"),
        "n128": d.Nu_128.map(lambda v: f"{v:.4f}"), "p": d.p_observed.map(lambda v: f"{v:.2f}"),
        "ext": d.Nu_extrapolated.map(lambda v: f"{v:.4f}"), "ref": d.ref_Hortmann.map(lambda v: f"{v:.3f}"),
        "err": d.err_ext_vs_Hortmann_pct.map(lambda v: f"{v:+.3f}"), "conv": d.convergence})
    return tabular(rows, "ccccccccl", ["$Ra$", "Nu $64^2$", "Nu $96^2$", "Nu $128^2$", "$p$", "Nu$_{ext}$",
                                       "Ref.", "Err. (\\%)", "Convergence"],
                   "Verification on the differentially heated cavity (Pr 0.71): mean wall Nusselt number on three "
                   "meshes, observed order $p$, Richardson-extrapolated value and its error against "
                   "\\citet{hortmann1990}.", "tab:verify")


def t_gci():
    f = TABLES / "T7_gci.csv"
    if not f.exists():
        return ""
    d = pd.read_csv(f)
    lab = {"mds": "MDS", "aph": "APH", "vented_fly_box_vent20": "VFB (20 mm)"}
    q = lambda s: s.split(":")[0].replace("zone_", "zone ").replace("domainAvg", "domain") + " " + \
        s.split(":")[1] if ":" in s else s  # noqa: E731
    rows = pd.DataFrame({"m": d.model.map(lab), "g": d.gravity, "q": d.quantity.map(lambda s: esc(q(s))),
                         "f": d.phi_fine.map(num), "md": d.phi_medium.map(num), "c": d.phi_coarse.map(num),
                         "p": d.p.map(lambda v: num(v)), "gci": d.gci_fine_pct.map(lambda v: num(v)),
                         "sd": d.temporal_sd_fine.map(lambda v: num(v)),
                         "conv": [c + (" (within unsteadiness)" if w else "")
                                  for c, w in zip(d.convergence, d.mesh_spread_within_unsteadiness)]})
    return tabular(rows, "lllrrrrrrl", ["Model", "$g$", "Quantity", "Fine", "Medium", "Coarse", "$p$",
                                        "GCI (\\%)", "Temporal sd", "Convergence"],
                   "Grid convergence \\citep{celik2008} of specimen-zone and domain quantities (excess over the supply "
                   "state; age of air in s; $U_{max}$ in m\\,s$^{-1}$).", "tab:gci", r"\scriptsize")


def t_cfd():
    f = TABLES / "T9_cfd_results_medium.csv"
    if not f.exists():
        return ""
    d = pd.read_csv(f)

    def pm(v, sd, nd=2):
        if v is None or (isinstance(v, float) and v != v):
            return "--"
        return num(v, nd) + (f" $\\pm$ {num(sd, nd)}" if sd and sd == sd and sd > 0.005 * max(1e-12, abs(v)) else "")
    rows = pd.DataFrame({
        "m": d.label.map(esc), "g": d.gravity, "z": d.zone.map(esc),
        "co2": [pm(v, s_) for v, s_ in zip(d.CO2_excess_ppm, d.CO2_late_sd_ppm)],
        "h2o": d.H2O_excess_mmol_mol.map(lambda v: "0" if v == v and abs(v) < 1e-4 else num(v, 3)),
        "t": d.T_excess_K.map(lambda v: "0" if v == v and abs(v) < 1e-4 else num(v, 3)),
        "age": [pm(v, s_) for v, s_ in zip(d.age_of_air_s, d.age_late_sd_s)],
        "rein": d.Re_inlet.map(lambda v: num(v, 0)),
        "ri": d.Ri_1g.map(lambda v: "0" if v == v and abs(v) < 1e-6 else num(v)),
        "ras": d.Ra_solutal_CO2_1g.map(lambda v: num(v, 0)),
        "bal": d.CO2_balance_rel_imbalance.map(lambda v: "--" if v != v else f"{100 * v:+.2f}")})
    body = tabular(rows, "lllrrrrrrrr", ["Model", "$g$", "Zone", "$\\Delta$CO$_2$ (ppm)", "$\\Delta$H$_2$O (mmol/mol)",
                                          "$\\Delta T$ (K)", "Age of air (s)", "Re$_{inlet}$", "Ri", "Ra$_{CO_2}$",
                                          "CO$_2$ bal. (\\%)"],
                   "Specimen environments (medium mesh): plateau excess over the supply or initial state in the specimen "
                   "zone ($\\pm$ temporal s.d.\\ over the last quarter of the run), mean age of air, inlet Reynolds "
                   "number, Richardson number (1\\,$g$), solutal Rayleigh number of the CO$_2$ excess (omitted by the "
                   "model) and the closure of the transient CO$_2$ balance. Zero entries are zero up to round-off.",
                   "tab:cfd", r"\scriptsize")
    return body


def t_assumptions():
    out = []
    for f in sorted((ROOT / "models").glob("*.yaml")):
        spec = yaml.safe_load(f.read_text())
        for a in spec.get("assumptions") or []:
            out.append({"model": brk(f.stem), "param": brk(a["param"]), "why": esc(a["why"])})
    d = pd.DataFrame(out)
    lines = [r"\footnotesize", r"\begin{longtable}{>{\raggedright\arraybackslash}p{0.17\linewidth}>{\raggedright\arraybackslash}p{0.22\linewidth}>{\raggedright\arraybackslash}p{0.55\linewidth}}",
             r"\caption{Every modelling assumption in the CFD models (all other numbers reference sourced "
             r"parameters).}\label{tab:assumptions}\\", r"\toprule Model & Parameter & Reason \\ \midrule \endfirsthead",
             # label only in the first head: a repeated \endhead caption would redefine it on every page
             r"\multicolumn{3}{l}{\emph{Table~\ref{tab:assumptions}, continued}}\\",
             r"\toprule Model & Parameter & Reason \\ \midrule \endhead"]
    for _, r in d.iterrows():
        lines.append(f"{r.model} & {r.param} & {r.why} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\normalsize", ""]
    return "\n".join(lines)


def t_splash_review():
    d = pd.read_csv(CURATED / "splash_field_review.csv")
    d = d[d.verdict.isin(["misattributed", "uncertain", "duplicate_of"])]
    lines = [r"\footnotesize", r"\begin{longtable}{r>{\raggedright\arraybackslash}p{0.2\linewidth}>{\raggedright\arraybackslash}p{0.12\linewidth}r>{\raggedright\arraybackslash}p{0.45\linewidth}}",
             r"\caption{SPLASH fields judged misattributed, uncertain or duplicated (likely source row "
             r"given).}\label{tab:splash}\\",
             r"\toprule \# & Field & Verdict & Source row & Reason \\ \midrule \endfirsthead",
             r"\multicolumn{5}{l}{\emph{Table~\ref{tab:splash}, continued}}\\",
             r"\toprule \# & Field & Verdict & Source row & Reason \\ \midrule \endhead"]
    for _, r in d.iterrows():
        src = "" if pd.isna(r.likely_source_id) else str(int(r.likely_source_id))
        lines.append(f"{r.splash_id} & {brk(r.field)} & {brk(r.verdict)} & {src} & {esc(r.reason)} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\normalsize", ""]
    return "\n".join(lines)


def t_items():
    d = pd.read_csv(TABLES / "T3a_checklist_items.csv")
    it = pd.read_csv(TABLES / "T4c_item_missingness.csv").set_index("item")
    rows = pd.DataFrame({"k": d.key, "l": d.label.map(esc), "g": d.group, "c": d.critical.map(lambda b: "yes" if b else ""),
                         "q": [f"{100 * it.loc[k, 'quantitative']:.0f}" for k in d.key],
                         "h": [f"{100 * it.loc[k, 'qualitative']:.0f}" for k in d.key],
                         "a": [f"{100 * it.loc[k, 'absent']:.0f}" for k in d.key]})
    return tabular(rows, "llllrrr", ["Item", "Description", "Group", "Critical", "Quant. (\\%)", "Qual. (\\%)",
                                     "Absent (\\%)"],
                   "The MI-CFD-HW checklist and its coverage across specimen-housing hardware (public sources).",
                   "tab:items")


def t_telemetry():
    t = pd.read_csv(TABLES / "T11_flight_ground.csv")
    w = pd.read_csv(CURATED / "eda_mission_windows.csv").set_index("mission")
    order = w.assign(s=pd.to_datetime(w.start_utc)).sort_values("s").index
    def fx(x, nd):
        v = f"{x:.{nd}f}"
        return v[1:] if v.startswith("-") and float(v) == 0 else v           # no "-0.00"

    def cell(r, nd):
        if r is None or pd.isna(r.offset_median):
            return "--"
        return f"{fx(r.offset_median, nd)} [{fx(r.offset_p25, nd)}, {fx(r.offset_p75, nd)}]"
    rows = []
    for m in [m for m in order if m in set(t.mission)]:
        s = t[t.mission == m].set_index("variable")
        get = lambda v: s.loc[v] if v in s.index else None
        r0 = s.iloc[0]
        rows.append({"m": m, "w": f"{r0.window_start} -- {r0.window_end}",
                     "lag": "--" if pd.isna(r0.ground_lag_h) else f"{int(r0.ground_lag_h)}",
                     "dt": cell(get("temperature"), 2), "drh": cell(get("humidity"), 1), "dco": cell(get("co2"), 0),
                     "dose": num(r0.mean_daily_dose_mGy)})
    return tabular(pd.DataFrame(rows), "llrllll",
                   ["Mission", "Habitation window", "Lag (h)", r"$\Delta T$ ($^\circ$C)", r"$\Delta$RH (\%)",
                    r"$\Delta$CO$_2$ (ppm)", r"Dose (mGy\,d$^{-1}$)"],
                   "ISS cabin minus ground-control environment in the OSDR Environmental Data App: median and "
                   "interquartile range of hourly flight $-$ ground differences after aligning the ground series by "
                   "its best lag, and the mean daily absorbed dose over the window. -- : not available (RR-9: EDA dates its "
                   "telemetry a year after its dose record, so the two do not overlap).", "tab:telemetry")


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("curated", t_curated), ("verification", t_verification), ("gci", t_gci), ("cfd", t_cfd),
                     ("assumptions", t_assumptions), ("splash_review", t_splash_review), ("items", t_items),
                     ("telemetry", t_telemetry)):
        (OUT / f"{name}.tex").write_text(fn())


if __name__ == "__main__":
    run()
    print(sorted(p.name for p in OUT.iterdir()))
