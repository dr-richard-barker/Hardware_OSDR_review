"""Core tests. Run: PYTHONPATH=src HWREVIEW_SNAPSHOT=2026-10-12 pytest -q"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("HWREVIEW_SNAPSHOT", "2026-10-12")
ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------- units / physics
def test_unit_conversions():
    from hwreview.cases import to_mol_s, to_mol_s_mass, to_W
    assert to_mol_s(1, "umol/s") == pytest.approx(1e-6)
    assert to_mol_s(10, "umol m-2 s-1", area_m2=0.1) == pytest.approx(1e-6)
    assert to_mol_s(22414.0, "mL/min") == pytest.approx(1 / 60)
    assert to_mol_s_mass(18.01528, "g/h", 18.01528) == pytest.approx(1 / 3600)
    assert to_W(86.4, "kJ/day") == pytest.approx(1.0)


def test_physics_sources():
    from hwreview import physics
    assert physics.D_CO2(20) == pytest.approx(14.7e-6)      # Monteith & Unsworth Table A.3
    assert physics.D_H2O(25) == pytest.approx(24.9e-6)
    a = physics.air(20)
    assert 1.4e-5 < a["nu"] < 1.6e-5 and 0.70 < a["Pr"] < 0.72
    assert physics.p_sat_water_kpa(20) == pytest.approx(2.339, rel=2e-3)   # IAPWS


# ---------------------------------------------------------------- crosswalk
def test_alias_and_split():
    from hwreview.crosswalk import aliases, split_components
    al, ac = aliases("Advanced Plant Habitat (APH)")
    assert "advanced plant habitat" in al and "APH" in ac
    assert split_components("Rodent Habitat, Hindlimb Unloading") == ["Rodent Habitat", "Hindlimb Unloading"]
    assert split_components("BRIC-PDFU (Petri Dish, Fixation Unit)") == ["BRIC-PDFU (Petri Dish, Fixation Unit)"]


def test_entities_known_links():
    from hwreview import crosswalk
    e = crosswalk.load_entities()
    aph = e[e.splash_ids.map(lambda v: 34 in v)].iloc[0]
    assert "2017" in aph.registry_ids
    mvp = e[e.splash_ids.map(lambda v: 36 in v)].iloc[0]
    assert "1403" not in mvp.registry_ids          # curated nolink (SPLASH alias error)
    assert not any(len(v) > 1 and set(v) == {10, 18} for v in e.splash_ids)


# ---------------------------------------------------------------- SPLASH integrity
def test_block_rule_excludes_displaced_fields():
    from hwreview.evidence import untrusted
    u = untrusted()
    assert (140, "specimen_types_supported") in u and (140, "gas_control") in u
    assert (140, "background") not in u and (34, "specimen_types_supported") not in u


# ---------------------------------------------------------------- classification
def test_classification_examples():
    c = pd.read_json(ROOT / "data" / "derived" / "classification.json").set_index("canonical_name")
    assert c.loc["Advanced Plant Habitat", "specimen_habitat"]
    assert "plant" in c.loc["Advanced Plant Habitat", "organism_classes_text"]
    rh = c[c.index.str.startswith("Rodent Habitat")].iloc[0]
    assert "rodent" in rh.organism_classes_text and rh.specimen_habitat
    assert c[c.index.str.startswith("Animal Access Unit")].iloc[0].role == "processing_fixation"


# ---------------------------------------------------------------- scorer
def test_scorer_rejects_storage_temperature():
    from hwreview.evidence import Text
    from hwreview.sufficiency import score_texts
    t = [Text("study", "OSD-x", "protocol", "", "Samples were stored at -80 °C. Seedlings grew at 22 °C on orbit.")]
    s = score_texts(t)
    assert s["E1"]["score"] == 1 and "22" in s["E1"]["quote"] and "-80" not in s["E1"]["quote"].split("22")[1]
    s2 = score_texts([Text("study", "OSD-y", "protocol", "", "Tissue was stored at -80 °C until RNA extraction.")])
    assert s2["E1"]["score"] == 0


def test_validation_reproducible():
    from hwreview import gold
    out = gold.run()
    assert out["rater_weighted_kappa"] > 0.8
    assert out["auto_presence_precision"] == 1.0


# ---------------------------------------------------------------- geometry
@pytest.fixture
def fixture_env(monkeypatch):
    monkeypatch.setenv("HWREVIEW_MODELS", str(FIX / "models"))
    monkeypatch.setenv("HWREVIEW_HARDWARE", str(FIX / "hardware"))
    import importlib
    from hwreview import geometry
    importlib.reload(geometry)
    yield geometry
    monkeypatch.delenv("HWREVIEW_MODELS")
    monkeypatch.delenv("HWREVIEW_HARDWARE")
    importlib.reload(geometry)


def test_stl_closed_and_volume(fixture_env, tmp_path):
    m = fixture_env.load("testbox")
    assert fixture_env.validate(m) == []
    info = fixture_env.write_stl(m, tmp_path)
    assert info["domain_watertight"]
    assert info["domain_volume_from_stl_mm3"] == pytest.approx(120 * 80 * 60)
    assert set(info["patch_roles"]) == {"walls", "inlet", "outlet"}


def test_unsourced_literal_is_refused(fixture_env, tmp_path):
    import yaml
    spec = yaml.safe_load((FIX / "models" / "testbox.yaml").read_text())
    spec["assumptions"] = [a for a in spec["assumptions"] if a["param"] != "zones[0].center"]
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(spec))
    os.environ["HWREVIEW_MODELS"] = str(tmp_path)
    with pytest.raises(ValueError, match="neither sourced"):
        fixture_env.load("bad")
    os.environ["HWREVIEW_MODELS"] = str(FIX / "models")


def test_hardware_yaml_values_are_sourced():
    """Every non-null parameter in hardware/*.yaml carries a source and a quote (or is user_supplied/derived)."""
    import yaml
    bad = []
    for f in sorted((ROOT / "hardware").glob("*.yaml")):
        d = yaml.safe_load(f.read_text())

        def walk(node, path):
            if isinstance(node, dict) and "value" in node:
                v = node["value"]
                if v is not None and not (isinstance(v, str) and v.strip().lower().startswith("n/a")):
                    if not node.get("source"):
                        bad.append(f"{f.name}:{path} no source")
                    if node.get("kind") not in ("derived", "user_supplied") and not node.get("quote"):
                        bad.append(f"{f.name}:{path} no quote")
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{path}.{k}" if path else k)
        walk(d, "")
    assert not bad, "\n".join(bad[:40])


def test_gci_recovers_known_order():
    from hwreview.gci import gci3
    h = [1.0, 1.41421356, 2.0]
    phi = [3.0 + 0.5 * x ** 2 for x in h]          # exact second-order behaviour, limit 3.0
    r = gci3(phi, h)
    assert r["p"] == pytest.approx(2.0, abs=1e-6)
    assert r["phi_ext"] == pytest.approx(3.0, abs=1e-9)
    assert r["convergence"] == "monotonic"


def test_passive_vent_is_dirichlet(fixture_env, tmp_path, monkeypatch):
    """A passive vent must impose the exterior state (fixedValue), not inletOutlet (zeroGradient at phi=0)."""
    import yaml
    from hwreview import cases, paths
    spec = yaml.safe_load((FIX / "models" / "testbox.yaml").read_text())
    spec["openings"] = [{"name": "vent", "role": "vent", "face": "xmax", "size": [20, 20], "center": [40, 30],
                         "outside": {"CO2": 1000}}]
    spec["assumptions"] += [{"param": "openings[0].size", "why": "t"}, {"param": "openings[0].center", "why": "t"},
                            {"param": "openings.vent.outside.CO2", "why": "t"}]
    (tmp_path / "ventbox.yaml").write_text(yaml.safe_dump(spec))
    monkeypatch.setenv("HWREVIEW_MODELS", str(tmp_path))
    monkeypatch.setattr(cases, "RUNS", tmp_path / "runs")
    case = cases.build("ventbox", "0g", "coarse", 2)
    co2 = (case / "0" / "CO2").read_text()
    block = co2[co2.index("domain_vent"):]
    assert "fixedValue" in block.split("}")[0] and "1000" in block.split("}")[0]
