"""Outils communs aux services F1-F4.

Règles (CLAUDE.md, D17, D20) :
- valeurs stockées en dixièmes (entiers) ; calculs exacts en SQL (entiers, numeric) ou en Fraction ;
- arrondi uniquement à la sortie, à 0,01, moitié loin de zéro (comme round(numeric, 2) de PostgreSQL) ;
- observation valide = qflag vide et mflag différent de P (pluie manquante présumée nulle).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

VALID = "o.qflag IS NULL AND o.mflag IS DISTINCT FROM 'P'"
UNITS = {"TMAX": "°C", "TMIN": "°C", "PRCP": "mm"}
REFERENCE = (1991, 2020)


def round2(x: Fraction | Decimal | int) -> float:
    """Arrondi à 0,01, moitié loin de zéro, à partir d'une valeur exacte."""
    if isinstance(x, Fraction):
        x = Decimal(x.numerator) / Decimal(x.denominator)
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def tenths(x: float) -> int:
    """Valeur saisie par l'utilisateur (°C ou mm) -> dixièmes entiers, comme dans les fichiers NOAA."""
    return int((Decimal(str(x)) * 10).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def unit_value(v: int | None) -> float | None:
    """Dixièmes -> unité physique (exact : une décimale)."""
    return None if v is None else float(Decimal(v) / 10)


@dataclass
class Area:
    """Zone géographique : un ou plusieurs pays (GM, SP) et/ou un rectangle lat/lon."""
    zones: list[str] | None = None
    bbox: tuple[float, float, float, float] | None = None  # lat_min, lat_max, lon_min, lon_max

    def sql(self, alias: str = "s") -> tuple[str, dict]:
        parts, params = [], {}
        if self.zones:
            parts.append(f"{alias}.zone = ANY(%(zones)s)")
            params["zones"] = self.zones
        if self.bbox:
            parts.append(f"{alias}.lat BETWEEN %(lat0)s AND %(lat1)s AND {alias}.lon BETWEEN %(lon0)s AND %(lon1)s")
            params.update(zip(("lat0", "lat1", "lon0", "lon1"), self.bbox, strict=True))
        return (" AND ".join(parts) or "TRUE"), params

    def describe(self) -> dict:
        return {"zones": self.zones, "bbox": list(self.bbox) if self.bbox else None}


def explain(conn, sql: str, params: dict) -> list[str]:
    """Plan d'exécution : en distribué, montre les tâches et les workers contactés (« Node: host=... »)."""
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (COSTS OFF) " + sql, params)
        return [r[0] for r in cur.fetchall()]


def fetch(conn, sql: str, params: dict) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
