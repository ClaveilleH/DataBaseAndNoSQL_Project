# Jeu de données : chiffres et anomalies

Calculé par `verify/data_report.py` directement depuis les fichiers NOAA `by_station` (sans la base). Périmètre : 774 stations, TMAX/TMIN/PRCP, 1991–2024.

## Stations et couples station-jour

| Zone | Stations | Mailles 0,5° | Station-jours 2015–2024 | Station-jours 1991–2014 (référence seule) |
| --- | --- | --- | --- | --- |
| GM | 589 | 213 | 2,029,108 | 4,240,777 |
| SP | 185 | 94 | 621,891 | 1,020,762 |

## Observations par élément

Valides = sans qflag et sans mflag P. Les observations 2015–2020 servent aussi à la référence 1991–2020.

| Zone | Élément | Période | Stations actives | Valides | Invalides (qflag) | P |
| --- | --- | --- | --- | --- | --- | --- |
| GM | TMAX | 2015–2024 | 474 | 1,662,847 | 7 | 0 |
| GM | TMAX | 1991–2014 | 541 | 3,572,600 | 97 | 0 |
| GM | TMIN | 2015–2024 | 474 | 1,662,826 | 18 | 0 |
| GM | TMIN | 1991–2014 | 541 | 3,571,251 | 119 | 0 |
| GM | PRCP | 2015–2024 | 579 | 2,010,884 | 6 | 0 |
| GM | PRCP | 1991–2014 | 585 | 4,208,967 | 43 | 0 |
| SP | TMAX | 2015–2024 | 183 | 598,648 | 289 | 0 |
| SP | TMAX | 1991–2014 | 175 | 1,002,404 | 333 | 0 |
| SP | TMIN | 2015–2024 | 183 | 603,741 | 209 | 0 |
| SP | TMIN | 1991–2014 | 175 | 994,030 | 268 | 0 |
| SP | PRCP | 2015–2024 | 184 | 604,505 | 5 | 0 |
| SP | PRCP | 1991–2014 | 175 | 965,962 | 9 | 0 |

Total : 21,460,068 observations brutes.

## Observations par année

| Année | GM | SP |
| --- | --- | --- |
| 1991 | 405,887 | 98,636 |
| 1992 | 415,668 | 99,708 |
| 1993 | 418,215 | 100,049 |
| 1994 | 427,005 | 99,854 |
| 1995 | 434,795 | 100,636 |
| 1996 | 437,498 | 101,120 |
| 1997 | 437,594 | 99,682 |
| 1998 | 450,801 | 98,970 |
| 1999 | 459,989 | 98,284 |
| 2000 | 452,603 | 96,343 |
| 2001 | 452,112 | 99,010 |
| 2002 | 445,693 | 98,593 |
| 2003 | 441,591 | 99,344 |
| 2004 | 437,454 | 100,319 |
| 2005 | 474,226 | 100,083 |
| 2006 | 491,871 | 99,656 |
| 2007 | 505,283 | 99,812 |
| 2008 | 526,836 | 175,498 |
| 2009 | 532,675 | 179,382 |
| 2010 | 536,985 | 180,170 |
| 2011 | 539,714 | 182,218 |
| 2012 | 542,045 | 184,970 |
| 2013 | 541,697 | 184,745 |
| 2014 | 544,840 | 185,924 |
| 2015 | 542,570 | 187,564 |
| 2016 | 544,730 | 190,421 |
| 2017 | 542,515 | 188,367 |
| 2018 | 539,373 | 188,462 |
| 2019 | 533,573 | 153,580 |
| 2020 | 532,292 | 190,115 |
| 2021 | 529,522 | 189,707 |
| 2022 | 526,892 | 188,462 |
| 2023 | 522,821 | 187,782 |
| 2024 | 522,300 | 142,937 |

## Anomalies présentes dans les données

Fréquence sur 1991–2024 (les trous et les débuts ou fins de station : sur 2015–2024), avec des exemples vérifiables dans les fichiers NOAA (valeurs en dixièmes).

| Anomalie | Fréquence | Exemples |
| --- | --- | --- |
| qflag I | 682 | GM000003218 1996-12-31 TMIN=-138<br>GM000003218 1997-01-01 TMAX=-151<br>GM000004155 2001-11-23 TMAX=-164 |
| qflag O | 320 | GME00121150 2017-06-29 PRCP=1969<br>GME00121282 2010-07-14 TMAX=302<br>GME00121366 2002-08-12 PRCP=1940 |
| PRCP trace (T) | 267 | SPW00013025 1991-01-08 PRCP=0 T<br>SPW00013025 1991-01-16 PRCP=0 T<br>SPW00013025 1991-03-13 PRCP=0 T |
| qflag N | 192 | GME00123382 2006-04-17 TMAX=0<br>GME00123382 2006-04-18 TMAX=0<br>GME00123382 2006-04-17 TMIN=0 |
| qflag S | 172 | GM000004155 1993-11-27 TMAX=1<br>GM000004155 2013-12-03 TMIN=-15<br>GME00102348 1993-02-04 TMIN=51 |
| station qui s'arrête pendant 2015-2024 | 131 | GM000002716 dernière observation 2022-04-14<br>GM000003218 dernière observation 2015-03-22<br>GME00102236 dernière observation 2019-04-07 |
| trou de plus de 30 jours (2015-2024) | 94 | GME00102169 du 2015-01-13 au 2015-03-19<br>GME00102169 du 2015-09-30 au 2015-11-01<br>GME00102169 du 2016-02-27 au 2016-04-08 |
| station qui commence pendant 2015-2024 | 32 | GM000002716 première observation 2022-04-14<br>GME00121486 première observation 2021-06-02<br>GME00122446 première observation 2015-04-01 |
| qflag K | 26 | GME00132550 1998-08-27 PRCP=1<br>GME00132550 1998-08-28 PRCP=1<br>GME00132550 1998-08-29 PRCP=1 |
| valeur extrême sans qflag (T < -40 °C, T > 48 °C, pluie > 200 mm) | 15 | SP000007038 2019-09-13 PRCP=2037<br>SPE00101043 1997-09-30 PRCP=2702<br>SPE00120152 1996-11-11 PRCP=2019 |
| qflag G | 8 | GME00121282 2000-02-02 TMAX=210<br>GME00129886 1998-07-11 TMIN=-125<br>SPE00156090 2019-05-01 TMAX=0 |
| qflag M | 3 | GME00121282 2000-02-03 TMIN=168<br>GME00121282 2000-02-06 TMIN=151<br>GME00121282 2000-02-07 TMIN=119 |
