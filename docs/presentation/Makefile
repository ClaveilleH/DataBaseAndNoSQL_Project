# make        : compile main.pdf
# make clean  : supprime les fichiers temporaires
# make view   : ouvre le PDF
TEX = main.tex
PDF = $(TEX:.tex=.pdf)
LATEXMK := $(shell command -v latexmk 2>/dev/null)

.PHONY: all clean distclean view

all: $(PDF)

$(PDF): $(TEX) pres.cls mybeamer.sty
ifeq ($(LATEXMK),)
	pdflatex -interaction=nonstopmode -halt-on-error $(TEX)
	pdflatex -interaction=nonstopmode -halt-on-error $(TEX)
else
	latexmk -pdf -interaction=nonstopmode $(TEX)
endif

clean:
	rm -f *.aux *.log *.nav *.snm *.out *.toc *.vrb *.fls *.fdb_latexmk *.synctex.gz

distclean: clean
	rm -f $(PDF)

view: $(PDF)
	xdg-open $(PDF) >/dev/null 2>&1 || true
