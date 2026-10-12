"""The project page may only quote numbers that exist as manuscript macros."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_site():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts/build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_template_placeholders_resolve():
    mod = _build_site()
    known = set(mod.macros()) | {"TABLE_ITEMS", "TABLE_VERIFY", "TABLE_CFD", "TABLE_CURATED", "TABLE_TELEMETRY", "MODEL_VIEWER",
                                 "REPO", "N_EXPLORER"}
    used = set(re.findall(r"\{\{(\w+)\}\}", (ROOT / "site/index.template.html").read_text()))
    assert used <= known, sorted(used - known)


def test_no_hand_typed_result_numbers():
    # decimals in running text must come from placeholders; allowed literals are listed here
    page = (ROOT / "site/index.template.html").read_text()
    page = re.sub(r"<pre>.*?</pre>", "", page, flags=re.S)
    text = re.sub(r"<[^>]+>|\{\{\w+\}\}", " ", page)
    allowed = {"4.0"}  # CC BY 4.0
    decimals = set(re.findall(r"\b\d+\.\d+\b", text)) - allowed
    assert not decimals, sorted(decimals)


def test_explorer_rows_are_specimen_habitats():
    mod = _build_site()
    rows = mod.habitats()
    assert rows and all(set(r) >= {"id", "n", "c", "t"} for r in rows)
    assert all(0 <= r["c"] <= 1 for r in rows)
