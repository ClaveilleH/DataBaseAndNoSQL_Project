"""Vérification indépendante de F3 : mois les plus anormaux d'une zone, depuis les fichiers NOAA.

Usage : uv run python -m verify.f3_anomalies --zone GM --years 2015 2024 [--element TMAX] [--top 10]

Définition (D17), pour TMAX ou TMIN :
- mois-station éligible : au moins 80 % des jours du mois ont une observation valide (sans qflag) ;
  sa moyenne = somme des valeurs valides / nombre de valeurs valides (dixièmes de °C) ;
- normale d'une station pour un mois calendaire : moyenne de ses moyennes mensuelles éligibles
  sur 1991-2020, si au moins 24 des 30 années sont éligibles (80 %) ;
- anomalie mois-station = moyenne du mois - normale ;
- anomalie de zone : moyenne des anomalies par maille de 0,5°, puis moyenne des mailles,
  pour que les régions denses en stations ne pèsent pas plus que les autres ;
  un mois de zone n'est classé que s'il couvre au moins 5 mailles ;
- classement : par valeur absolue de l'anomalie de zone, décroissante ; égalités : année, mois.
Calcul exact en fractions, arrondi à 0,01 °C seulement à l'affichage.
"""

import argparse
import calendar
import json
from collections import defaultdict
from datetime import date
from fractions import Fraction

from verify.noaa import records, round2, stations

REF = (1991, 2020)
MIN_SHARE = Fraction(8, 10)
MIN_REF_YEARS = 24
MIN_CELLS = 5


def monthly_means(station: str, element: str, first: int, last: int) -> dict[tuple[int, int], Fraction]:
    """Moyenne des mois-station éligibles, en dixièmes."""
    total, n = defaultdict(int), defaultdict(int)
    for d, v, _m, q, _s in records(station, element, date(first, 1, 1), date(last, 12, 31)):
        if q is None:
            total[(d.year, d.month)] += v
            n[(d.year, d.month)] += 1
    return {ym: Fraction(total[ym], n[ym]) for ym in n
            if n[ym] >= MIN_SHARE * calendar.monthrange(*ym)[1]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--zone", required=True)
    p.add_argument("--years", type=int, nargs=2, required=True)
    p.add_argument("--element", default="TMAX", choices=["TMAX", "TMIN"])
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--out")
    a = p.parse_args()

    meta = stations(a.zone)
    # anomalies[(année, mois)][maille] = liste des anomalies des stations de la maille
    anomalies: dict[tuple[int, int], dict[tuple, list[Fraction]]] = defaultdict(lambda: defaultdict(list))
    for sid in sorted(meta):
        means = monthly_means(sid, a.element, min(REF[0], a.years[0]), max(REF[1], a.years[1]))
        for month in range(1, 13):
            ref = [m for (y, mo), m in means.items() if mo == month and REF[0] <= y <= REF[1]]
            if len(ref) < MIN_REF_YEARS:
                continue
            normal = sum(ref) / len(ref)
            for y in range(a.years[0], a.years[1] + 1):
                if (y, month) in means:
                    anomalies[(y, month)][meta[sid]["cell"]].append(means[(y, month)] - normal)

    ranked = []
    for (y, mo), cells in anomalies.items():
        if len(cells) < MIN_CELLS:
            continue
        cell_means = [sum(v) / len(v) for v in cells.values()]
        anomaly = sum(cell_means) / len(cell_means) / 10  # dixièmes -> °C
        ranked.append({"year": y, "month": mo, "anomaly_c": round2(anomaly),
                       "cells": len(cells), "stations": sum(len(v) for v in cells.values())})
    ranked.sort(key=lambda r: (-abs(r["anomaly_c"]), r["year"], r["month"]))
    params = {k: str(v) for k, v in vars(a).items() if k != "out"}
    payload = {"service": "F3", "params": params, "months": ranked}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
    print(json.dumps({"params": params, "ranked_months": len(ranked), "top": ranked[:a.top]}, indent=1))


if __name__ == "__main__":
    main()
