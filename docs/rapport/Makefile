# Compilation avec pdflatex
all: rapport.pdf

rapport.pdf: rapport.tex
	pdflatex rapport.tex
	pdflatex rapport.tex

# Nettoyage des fichiers générés
clean:
	rm -f rapport.aux rapport.log rapport.toc rapport.out rapport.pdf