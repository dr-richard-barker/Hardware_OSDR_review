"""The ISS cabin values used by the CFD models must be the EDA statistics they claim to be."""
from pathlib import Path

import yaml

from hwreview import eda, telemetry

ROOT = Path(__file__).resolve().parents[1]


def test_eda_snapshot_checksums():
    eda.verify_checksums()


def test_qc_removes_the_rr1_co2_fill():
    # EDA's RR-1 flight CO2 holds 2646 ppm for 153 h from 2014-09-21: a fill, not a measurement
    raw, _ = eda.telemetry("RR-1", qc=False)
    qc, rep = eda.telemetry("RR-1")
    assert (raw.co2_iss == 2646).sum() >= 1800
    assert rep["co2_iss:held"] >= 1800 and (qc.co2_iss == 2646).sum() < 50


def test_cabin_yaml_matches_eda_statistics():
    cab = yaml.safe_load((ROOT / "hardware/_iss_cabin.yaml").read_text())["environment"]
    st = telemetry.cabin_rr1(write=False)
    st = st[(st.column == "iss") & (st.window == "RR-1 habitation (QC)")].set_index("variable")
    for key, var, nd in (("co2_ppm", "co2", 0), ("temperature_C", "temperature", 1), ("rh_percent", "humidity", 1)):
        rec = cab[key]
        assert round(st.loc[var, "median"], nd) == rec["value"], key
        lo, hi = rec["range_p01_p99"]
        assert round(st.loc[var, "p01"], nd) == lo and round(st.loc[var, "p99"], nd) == hi, key


def test_choi_ranges_equal_the_ground_column():
    # the superseded literature ranges are EDA's ground extremes, not its flight extremes
    st = telemetry.cabin_rr1(write=False)
    st = st[st.window == "Choi 2020 (raw)"].set_index(["variable", "column"])
    old = yaml.safe_load((ROOT / "hardware/_iss_cabin.yaml").read_text())["superseded_choi_2020"]
    for key, var in (("co2_ppm", "co2"), ("temperature_C", "temperature"), ("rh_percent", "humidity")):
        lo, hi = old[key]["value"]
        assert (st.loc[(var, "ground"), "min"], st.loc[(var, "ground"), "max"]) == (lo, hi)
        assert (st.loc[(var, "iss"), "min"], st.loc[(var, "iss"), "max"]) != (lo, hi)
