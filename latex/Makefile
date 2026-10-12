# Manuscript build: one LaTeX source -> PDF (latexmk), DOCX and HTML (pandoc).
#   make            all three
#   make pdf | docx | html | check | clean
# Outputs land in latex/output/. Figures are read from ../results/figures
# (PDF for LaTeX, PNG for pandoc); numbers come from ../results/macros.tex.

SRC      := manuscript.tex
SUPP     := supplement.tex
BIB      := references.bib
OUT      := output
BUILD    := build
PANDOC   := pandoc
PY       := ../.venv/bin/python

.PHONY: all pdf docx html check clean
all: pdf docx html

$(OUT) $(BUILD):
	mkdir -p $@

pdf: | $(OUT) $(BUILD)
	latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(BUILD) $(SRC)
	latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=$(BUILD) $(SUPP)
	cp $(BUILD)/manuscript.pdf $(BUILD)/supplement.pdf $(OUT)/

$(BUILD)/pandoc.tex: $(SRC) ../results/macros.tex pandoc_prep.py | $(BUILD)
	$(PY) pandoc_prep.py $(SRC) $@

docx: $(BUILD)/pandoc.tex | $(OUT)
	cd $(BUILD) && $(PANDOC) pandoc.tex -f latex -t docx --citeproc --bibliography=../$(BIB) \
	  --resource-path=.:..:../../results/figures -o ../$(OUT)/manuscript.docx

html: $(BUILD)/pandoc.tex | $(OUT)
	cd $(BUILD) && $(PANDOC) pandoc.tex -f latex -t html5 --standalone --mathml --citeproc \
	  --bibliography=../$(BIB) --embed-resources --resource-path=.:..:../../results/figures \
	  --metadata title="$$(grep -m1 '\\\\title{' ../$(SRC) | sed 's/.*title{\(.*\)}.*/\1/')" \
	  --css=../html.css -o ../$(OUT)/manuscript.html

check:
	$(PY) check_tex.py $(SRC) $(SUPP)

clean:
	rm -rf $(BUILD)
