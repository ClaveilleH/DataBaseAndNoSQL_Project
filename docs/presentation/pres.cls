% Classe Beamer perso — à placer à côté de main.tex
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{pres}[2026/10/29 Classe perso pour presentations Beamer]

% Les options passées à \documentclass (ex. aspectratio=169) sont transmises à beamer
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{beamer}}
\ProcessOptions\relax
\LoadClass[11pt]{beamer}

\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage[french]{babel}
\RequirePackage{graphicx}
\RequirePackage{mybeamer}

\endinput
