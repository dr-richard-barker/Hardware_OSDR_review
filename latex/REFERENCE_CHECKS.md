# Manual reference checks

`scripts/check_refs.py` verifies every DOI against Crossref (title, year, volume, first
author). Entries Crossref cannot fully verify are checked by hand here.

| key | what was checked | source opened | date |
|---|---|---|---|
| celik2008 | author list (Crossref lists none) | ASME JFE numerical-accuracy policy PDF, byline "Ismail B. Celik, Urmila Ghia, Patrick J. Roache and Christopher J. Freitas" (qa12.asme.org/.../JFENumAccuracy.pdf) | 2026-10-12 |
| hortmann1990 | DOI (an earlier draft carried a wrong DOI, 10.1002/fld.1650110207 = Steppeler 1990) and the third author's spelling, Scheuerer | Crossref bibliographic query | 2026-10-12 |
| gjesdal2003 | benchmark Nu values 2.243/4.519/8.800 (de Vahl Davis) and 2.245/4.522/8.825 (Hortmann et al.), Table 1 | arXiv:physics/0305049 PDF | 2026-10-12 |
| monteith2008 | D_CO2 and D_H2O tables (Table A.3) | photobiologyPlants R/D-water-CO2.R (transcription of Table A.3) | 2026-10-12 |
