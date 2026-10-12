# Hardware_OSDR_review - reproduce every result from the frozen snapshot.
#
#   make setup      create .venv and install pinned requirements
#   make analysis   crosswalk -> classification -> sufficiency -> meta-analysis -> validation -> figures
#   make verify     CFD verification (heated cavity ladders, diffusion) - needs Docker
#   make cfd        Tier-A hardware campaign (0 g / 1 g, mesh ladders) + animation runs - needs Docker, ~2-4 h on 12 cores
#   make post       post-processing, GCI, animations, ortho sheets
#   make paper      macros + manuscript PDF / DOCX / HTML
#   make check      tests, reference check, manuscript pre-flight, manifest
#   make zenodo     archive for deposit (dist/)
#   make site       GitHub Pages site in docs/ from the results
#   make fetch      re-download the NASA sources into a NEW dated snapshot (network)
#
# The analysis reads data/raw/$(SNAPSHOT); change it only to re-run on a new snapshot.

SNAPSHOT ?= 2026-10-12
PY       := .venv/bin/python
RUN      := HWREVIEW_SNAPSHOT=$(SNAPSHOT) PYTHONPATH=src $(PY)
MODELS   := aph aph_fanmax mds vented_fly_box_vent20 vented_fly_box_vent60 aqh

.PHONY: setup fetch analysis verify cfd post paper check zenodo site all

all: analysis post paper check

setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

fetch:
	PYTHONPATH=src $(PY) -m hwreview.fetch
	PYTHONPATH=src $(PY) -m hwreview.eda

analysis:
	$(RUN) -m hwreview.consistency
	$(RUN) -m hwreview.crosswalk
	$(RUN) -m hwreview.classify
	$(RUN) -m hwreview.sufficiency
	$(RUN) -m hwreview.meta
	$(RUN) -m hwreview.gold
	$(RUN) -m hwreview.curated
	$(RUN) -m hwreview.figures_meta
	$(RUN) -m hwreview.telemetry

verify:
	$(RUN) -m hwreview.verify_cfd --only diffusion
	$(RUN) -m hwreview.verify_cfd --only cavity --ra 1e4 --n 64 96 128
	$(RUN) -m hwreview.verify_cfd --only cavity --ra 1e5 --n 64 96 128
	$(RUN) -m hwreview.verify_cfd --only cavity --ra 1e6 --n 64 96 128
	$(RUN) -c "from hwreview import verify_cfd; verify_cfd.summarise()"

cfd:
	$(RUN) -m hwreview.campaign --np 12
	$(RUN) -m hwreview.campaign --anim --np 12

post:
	$(RUN) -m hwreview.ortho $(MODELS)
	$(RUN) -m hwreview.results
	$(RUN) -m hwreview.gci
	$(RUN) -c "from hwreview import verify_cfd; verify_cfd.summarise()"

paper:
	$(RUN) -m hwreview.curated
	$(RUN) -m hwreview.macros
	$(RUN) -m hwreview.tables_tex
	$(MAKE) -C latex all

check:
	$(RUN) -m pytest -q
	$(PY) scripts/check_refs.py
	$(PY) latex/check_tex.py manuscript.tex supplement.tex
	$(PY) scripts/check_manifest.py

zenodo: check
	$(PY) scripts/make_zenodo.py

site:
	$(PY) scripts/build_site.py
