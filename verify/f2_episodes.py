"""Vérification indépendante de F2 : épisodes prolongés, calculés depuis les fichiers NOAA.

Usage : uv run python -m verify.f2_episodes --zone SP --start 2015-01-01 --end 2024-12-31 \
            --element TMAX --threshold 400 --min-days 3 [--out resultat.json]

Définition (D17) :
- un jour compte s'il a une observation de l'élément, sans qflag, et valeur >= seuil (dixièmes) ;
- un épisode est une suite maximale de dates consécutives qui comptent, d'au moins --min-days jours ;
  un jour absent, invalide (qflag) ou sous le seuil coupe l'épisode ; les dates sont continues,
  donc un épisode du 30 décembre au 2 janvier est un seul épisode ;
- seuls les jours de la période [start, end] sont considérés (un épisode est tronqué aux bornes) ;
- intensité : dépassement moyen au-dessus du seuil et valeur maximale, en °C ou mm.
Tri canonique : station, date de début.
"""

import argparse
import json
from datetime import date, timedelta
from fractions import Fraction

from verify.noaa import records, round2, stations, valid


def episodes(station: str, element: str, start: date, end: date, threshold: int, min_days: int) -> list[dict]:
    days = [(d, v) for d, v, m, q, _s in records(station, element, start, end) if valid(m, q) and v >= threshold]
    found, run = [], []
    for d, v in days + [(None, None)]:  # sentinelle pour fermer le dernier épisode
        if run and (d is None or d - run[-1][0] != timedelta(days=1)):
            if len(run) >= min_days:
                # Unités physiques (°C ou mm), comme la sortie du service F2.
                excess = Fraction(sum(x - threshold for _, x in run), len(run) * 10)
                found.append({
                    "station": station, "start": run[0][0].isoformat(), "end": run[-1][0].isoformat(),
                    "days": len(run), "mean_excess": round2(excess), "max_value": max(x for _, x in run) / 10,
                })
            run = []
        if d is not None:
            run.append((d, v))
    return found


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--zone", required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--element", default="TMAX", choices=["TMAX", "TMIN", "PRCP"])
    p.add_argument("--threshold", type=int, required=True, help="seuil en dixièmes (400 = 40,0 °C)")
    p.add_argument("--min-days", type=int, default=3)
    p.add_argument("--out")
    a = p.parse_args()

    result = []
    for sid in sorted(stations(a.zone)):
        result += episodes(sid, a.element, a.start, a.end, a.threshold, a.min_days)
    params = {k: str(v) for k, v in vars(a).items() if k != "out"}
    payload = {"service": "F2", "params": params, "count": len(result), "episodes": result}
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
    longest = sorted(result, key=lambda e: (-e["days"], -e["mean_excess"], e["station"], e["start"]))[:10]
    print(json.dumps({"params": params, "count": len(result), "longest": longest}, indent=1))


if __name__ == "__main__":
    main()
