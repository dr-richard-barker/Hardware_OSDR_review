# Hardware_OSDR_review

**Which spaceflight biology hardware can be modelled?** A metadata audit of NASA's
space-biology hardware catalogues, a minimum-information checklist for computational fluid
dynamics (CFD) of specimen environments, literature-curated hardware specifications, and
verified three-dimensional transient OpenFOAM models of the hardware whose parameters can be
sourced - each run as flight (0 g) and ground control (1 g).

Every number in the manuscript is generated from the files in this repository
(`results/macros.tex`); every hardware value carries its source and a verbatim quotation;
every CFD dimension is either a reference to a sourced value or a declared assumption.

Project page: <https://dr-richard-barker.github.io/Hardware_OSDR_review/> (generated from the
results by `scripts/build_site.py`).

## What is here

| Path | Contents |
|---|---|
| `data/raw/2026-10-12/` | Frozen snapshot of the three public NASA sources with SHA-256 sums: SPLASH instrument catalogue, OSDR hardware registry (with payload and experiment records), OSDR study platform field and per-dataset metadata |
| `data/curated/` | Reviewed decisions: SPLASH field verdicts and the displaced-row rule, crosswalk and role overrides, the blind-rater validation set, the quote-audit sample and results |
| `data/derived/` | Hardware entities (crosswalk), classification |
| `hardware/` | Curated specification per hardware item (`SCHEMA.md`, `CURATION_NOTES.md`, `QUOTE_AUDIT.md`); `_iss_cabin.yaml` holds sourced ISS cabin conditions |
| `models/` | CFD model definitions for the CFD-ready (Tier A) hardware |
| `src/hwreview/` | The pipeline (one module per stage, below) |
| `results/tables/`, `results/figures/`, `results/fields/` | Tables, figures, orthographic sheets, animations, run time series, VTK field archives |
| `latex/` | Manuscript and supplement sources; `make -C latex` builds PDF, DOCX and HTML into `latex/output/` |
| `tests/` | `pytest` suite, including a synthetic CFD fixture |
| `openfoam/docker/IMAGE.md` | The pinned OpenFOAM v2606 image |
| `site/`, `docs/` | Project page template and the GitHub Pages site generated from it (`make site`) |
| `MANIFEST.tsv` | Every output file and the script that produces it (`scripts/check_manifest.py` fails on undescribed files) |

## Pipeline

| Stage | Module | Output |
|---|---|---|
| Snapshot the sources | `fetch` | `data/raw/<date>/` |
| SPLASH internal consistency | `consistency` | `T0_splash_consistency.csv` |
| Crosswalk SPLASH / registry / study platforms | `crosswalk` | `entities.json`, links, proposals |
| Role, organisms, platform, nutrient delivery | `classify` | `T1`, `T2`, `T2b` |
| MI-CFD-HW checklist scores and tiers | `sufficiency` | `T3*` |
| Meta-analysis | `meta` | `T4*` |
| Scorer validation against two blind raters | `gold` | `T5*` |
| Tiers after literature curation | `curated` | `T6_curated_tiers.csv` |
| CFD verification (heated cavity, diffusion) | `verify_cfd` | `T8*`, `V_*` |
| Geometry, drawings | `geometry`, `ortho` | `ortho_<model>` sheets |
| OpenFOAM cases and campaign | `cases`, `campaign`, `foam` | `runs/` (not archived); `campaign --anim` adds medium-mesh reruns with dense field output used only for the animations (checked against the production runs in `T10`) |
| Post-processing, GCI, results | `post`, `gci`, `results` | `T7_gci.csv`, `T9_*`, cards, slices, animations, VTK |
| Manuscript numbers | `macros` | `results/macros.tex` |

## Reproduce

```bash
make setup      # Python 3.14 venv with pinned requirements
make analysis   # catalogue -> crosswalk -> classification -> sufficiency -> meta-analysis -> validation -> figures
make verify     # CFD verification (Docker + OpenFOAM v2606 image, see openfoam/docker/IMAGE.md)
make cfd        # Tier-A campaign, 0 g and 1 g, mesh ladders
make post       # drawings, results, GCI
make paper      # macros + PDF / DOCX / HTML
make check      # tests, Crossref reference check, manuscript pre-flight, manifest
make zenodo     # dist/ archive for deposit
make site       # GitHub Pages site in docs/
```

`make fetch` downloads a new dated snapshot; the analysis reads the snapshot named by
`SNAPSHOT` (default `2026-10-12`). No credentials are needed and no personal data is sent
to any service.

## What is in git and what is only in the Zenodo deposit

Everything browsable lives in git: code, the raw snapshot, curated files, models, tables,
figures, animations, the manuscript sources and their PDF/DOCX/HTML builds. The VTK field
time series of the medium-mesh runs (`results/fields/vtk_*.tar.gz`, tens of MB each) are
too large for git and are included only in the Zenodo archive built by `make zenodo`.
The raw OpenFOAM run directories (`runs/`) are archived nowhere; `make cfd` regenerates them.

## Key conventions

* **Provenance.** `hardware/*.yaml` records are `{value, unit, source, url, quote, kind}`;
  `tests/test_core.py` fails on any non-null value without a source or quote. A model
  (`models/*.yaml`) refuses any number that is neither a `ref` into a hardware file nor a
  listed assumption.
* **Untrusted catalogue fields.** SPLASH records #121-147 carry descriptive fields displaced
  from neighbouring rows; they are excluded (`data/curated/splash_block_rule.yaml`).
* **Tiers.** A: every critical checklist item (enclosure, specimen container, ventilation
  mode, airflow - waived for sealed or passive hardware -, temperature, specimen) sourced;
  only Tier A hardware is modelled.

## Licence and citation

Code: MIT (`LICENSE`). Data, curated specifications, figures and manuscript: CC BY 4.0
(`LICENSE-DATA.md`). Cite via `CITATION.cff`. SPLASH data were obtained from NASA's Space
Life Sciences Archive of Scientific Hardware (SPLASH).
