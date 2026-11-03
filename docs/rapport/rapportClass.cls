\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{rapportClass}[2025/09/17 Classe perso pour rapport]

\LoadClass[a4paper,12pt]{report} % on part de "report"

% Packages de base
\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage[french]{babel}
\RequirePackage{graphicx}
\RequirePackage{hyperref}                % Liens cliquables
\RequirePackage{amsmath, amssymb}        % Maths
\RequirePackage{listings}                % Pour afficher du code
\RequirePackage{xcolor}                  % Couleurs (utile pour le code)
\usepackage{pgfplotstable}               % Pour les tableaux
\pgfplotsset{compat=1.18}                % Compatibilité pgfplots
\usepackage{float}                       % Pour forcer la position des figures

\RequirePackage{lipsum}                  % Générer du texte factice


% Packages supplémentaires pour les tableaux
\usepackage{multirow}
\usepackage{array}
\usepackage{float}


% Marges et page
\usepackage{geometry}
\geometry{
    a4paper,         % format A4
    left=2.5cm,        % marge gauche
    right=2.5cm,       % marge droite
    top=2cm,         % marge haute
    bottom=2cm,      % marge basse
    headheight=15pt, % hauteur de l'en-tête
    includehead,     % inclure l'en-tête dans la hauteur de page
    includefoot      % inclure le pied de page dans la hauteur de page
}


% En-têtes et pieds de page
% --- Configuration fancyhdr ---
\RequirePackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{Rapport de Projet}
\fancyhead[C]{M1 Informatique}
% \fancyhead[R]{Hugo CLAVEILLE}
\fancyhead[R]{\leftmark} % Titre du chapitre courant
\fancyfoot[C]{\thepage}
\setlength{\headwidth}{\textwidth} % largeur de l'en-tête = largeur du texte


\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}
% \renewcommand{cmd}{def}
\usepackage{lmodern}  % Latin Modern
\usepackage[T1]{fontenc}



\usepackage{titlesec}   % pour modifier l'apparence des chapitres
% --- Redéfinir le style des chapitres ---
\titleformat{\chapter}[hang]
  {\normalfont\huge\bfseries}
  {\thechapter.}
  {1em}
  {}


% Redéfinition de \chaptermark
\renewcommand{\chaptermark}[1]{%
  \markboth{#1}{}%
}


\setlength{\parskip}{0.8em} % espace entre les paragraphes