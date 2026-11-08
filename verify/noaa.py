"""Lecture directe des fichiers NOAA by_station, sans la base (vérification indépendante).

N'utilise que la bibliothèque standard : aucun code partagé avec ingest/ ni avec les services,
pour que la vérification ne reproduise pas leurs éventuelles erreurs.
"""

import csv
import gzip
from collections.abc import Iterator
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BY_STATION = ROOT / "data" / "raw" / "by_station"
STATIONS_CSV = ROOT / "data" / "stations_selected.csv"


def stations(zone: str | None = None) -> dict[str, dict]:
    """Stations retenues (id -> métadonnées), éventuellement limitées à une zone (GM, SP)."""
    with STATIONS_CSV.open(encoding="utf-8") as f:
        rows = {r["id"]: r for r in csv.DictReader(f) if zone is None or r["zone"] == zone}
    for r in rows.values():
        # Maille de 0,5° : même définition que stations.cell_lat / cell_lon dans sql/schema.sql.
        r["cell"] = (int(float(r["lat"]) * 2 // 1), int(float(r["lon"]) * 2 // 1))
    return rows


def records(station: str, element: str, start: date, end: date) -> Iterator[tuple]:
    """Observations d'une station pour un élément entre deux dates incluses.

    Renvoie (date, valeur entière en dixièmes, mflag, qflag, sflag) ; flag vide -> None.
    """
    lo, hi = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    with gzip.open(BY_STATION / f"{station}.csv.gz", "rt", encoding="ascii") as f:
        for line in f:
            _sid, day, elem, value, mflag, qflag, sflag, _obs_time = line.rstrip("\n").split(",")
            if elem == element and lo <= day <= hi:
                yield (date(int(day[:4]), int(day[4:6]), int(day[6:])), int(value),
                       mflag or None, qflag or None, sflag or None)


def round2(x: Fraction) -> float:
    """Arrondi à 2 décimales, moitié loin de zéro, comme round(numeric, 2) de PostgreSQL.

    Le round() de Python arrondit au pair et part d'un flottant : 13,125 donnerait 13,12 au lieu de 13,13.
    """
    exact = Decimal(x.numerator) / Decimal(x.denominator)
    return float(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
