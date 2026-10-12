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
             f"\\begin{{tabular}}{{{spec}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    for _, r in df.iterrows():
        lines.append(" & ".join(str(x) for x in r.values) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
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
                         "conv": d.convergence})
    return tabular(rows, "lllrrrrrl", ["Model", "$g$", "Quantity", "Fine", "Medium", "Coarse", "$p$",
                                       "GCI (\\%)", "Convergence"],
                   "Grid convergence \\citep{celik2008} of specimen-zone and domain quantities (excess over the supply "
                   "state; age of air in s; $U_{max}$ in m\\,s$^{-1}$).", "tab:gci", r"\scriptsize")


def t_cfd():
    f = TABLES / "T9_cfd_results_medium.csv"
    if not f.exists():
        return ""
    d = pd.read_csv(f)
    rows = pd.DataFrame({"m": d.label.map(esc), "g": d.gravity, "z": d.zone.map(esc),
                         "co2": d.CO2_excess_ppm.map(num), "h2o": d.H2O_excess_mmol_mol.map(num),
                         "t": d.T_excess_K.map(lambda v: num(v, 3)), "age": d.age_of_air_s.map(num),
                         "u": d.U_max_m_s.map(lambda v: num(v, 3)), "re": d.Re.map(lambda v: num(v, 0)),
                         "ri": d.Ri_1g.map(num), "bal": d.CO2_balance_rel_imbalance.map(num)})
    return tabular(rows, "lllrrrrrrrr", ["Model", "$g$", "Zone", "$\\Delta$CO$_2$ (ppm)",
                                         "$\\Delta$H$_2$O (mmol/mol)", "$\\Delta T$ (K)", "Age (s)",
                                         "$U_{max}$ (m/s)", "Re", "Ri (1 g)", "CO$_2$ imbalance"],
                   "Specimen-environment results (medium mesh, end of run): excess over the supply/initial state in the "
                   "specimen zone, its age of air, peak velocity, Reynolds and Richardson numbers, and the relative "
                   "closure of the transient CO$_2$ balance.", "tab:cfd", r"\scriptsize")


def t_assumptions():
    out = []
    for f in sorted((ROOT / "models").glob("*.yaml")):
        spec = yaml.safe_load(f.read_text())
        for a in spec.get("assumptions") or []:
            out.append({"model": esc(f.stem), "param": esc(a["param"]), "why": esc(a["why"])})
    d = pd.DataFrame(out)
    lines = [r"\footnotesize", r"\begin{longtable}{p{0.16\linewidth}p{0.22\linewidth}p{0.56\linewidth}}",
             r"\caption{Every modelling assumption in the CFD models (all other numbers reference sourced "
             r"parameters).}\label{tab:assumptions}\\", r"\toprule Model & Parameter & Reason \\ \midrule \endhead"]
    for _, r in d.iterrows():
        lines.append(f"{r.model} & {r.param} & {r.why} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\normalsize", ""]
    return "\n".join(lines)


def t_splash_review():
    d = pd.read_csv(CURATED / "splash_field_review.csv")
    d = d[d.verdict.isin(["misattributed", "uncertain", "duplicate_of"])]
    lines = [r"\footnotesize", r"\begin{longtable}{rp{0.2\linewidth}p{0.12\linewidth}rp{0.45\linewidth}}",
             r"\caption{SPLASH fields judged misattributed, uncertain or duplicated (likely source row "
             r"given).}\label{tab:splash}\\",
             r"\toprule \# & Field & Verdict & Source row & Reason \\ \midrule \endhead"]
    for _, r in d.iterrows():
        src = "" if pd.isna(r.likely_source_id) else str(int(r.likely_source_id))
        lines.append(f"{r.splash_id} & {esc(r.field)} & {esc(r.verdict)} & {src} & {esc(r.reason)} \\\\")
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


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("curated", t_curated), ("verification", t_verification), ("gci", t_gci), ("cfd", t_cfd),
                     ("assumptions", t_assumptions), ("splash_review", t_splash_review), ("items", t_items)):
        (OUT / f"{name}.tex").write_text(fn())


if __name__ == "__main__":
    run()
    print(sorted(p.name for p in OUT.iterdir()))
