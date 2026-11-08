"""F2 — Épisodes prolongés : suites de jours consécutifs au-dessus d'un seuil (définition D17).

Un jour compte s'il a une observation valide de l'élément avec valeur >= seuil. Les épisodes sont
des suites de dates consécutives (méthode « gaps and islands » : date - rang est constant dans
une suite), donc un jour absent, invalide ou sous le seuil coupe l'épisode, et un épisode
décembre-janvier reste un seul épisode. La fenêtre est découpée par station, la colonne de
distribution : en distribué, chaque worker calcule entièrement les épisodes de ses stations.
"""

from datetime import date
from fractions import Fraction

from weatherscope.services.common import UNITS, VALID, Area, fetch, round2, unit_value

SQL = f"""
WITH days AS (
    SELECT o.station, o.date, o.value
    FROM observations o JOIN stations s ON s.id = o.station
    WHERE {{area}} AND o.element = %(element)s AND o.date BETWEEN %(start)s AND %(end)s
      AND {VALID} AND o.value >= %(threshold)s
), runs AS (
    SELECT station, date, value,
           date - (row_number() OVER (PARTITION BY station ORDER BY date))::int AS grp
    FROM days
)
SELECT station, min(date) AS start, max(date) AS end, count(*) AS days,
       sum(value - %(threshold)s) AS excess_sum, max(value) AS max_value
FROM runs
GROUP BY station, grp
HAVING count(*) >= %(min_days)s
ORDER BY station, start
"""


def query(area: Area, element: str, start: date, end: date, threshold: int, min_days: int) -> tuple[str, dict]:
    where, params = area.sql()
    return SQL.format(area=where), {**params, "element": element, "start": start, "end": end,
                                    "threshold": threshold, "min_days": min_days}


def episodes(conn, area: Area, element: str, start: date, end: date, threshold: int, min_days: int) -> dict:
    """threshold en dixièmes (400 = 40,0 °C ; 100 = 10,0 mm)."""
    sql, params = query(area, element, start, end, threshold, min_days)
    rows = []
    for r in fetch(conn, sql, params):
        rows.append({
            "station": r["station"], "start": r["start"].isoformat(), "end": r["end"].isoformat(),
            "days": r["days"],
            "mean_excess": round2(Fraction(r["excess_sum"], r["days"] * 10)),  # unité physique
            "max_value": unit_value(r["max_value"]),
            "sources": {"station": r["station"], "element": element,
                        "start": r["start"].isoformat(), "end": r["end"].isoformat()},
        })
    return {"service": "F2", "unit": UNITS[element],
            "params": {**area.describe(), "element": element, "start": start.isoformat(), "end": end.isoformat(),
                       "threshold": unit_value(threshold), "min_days": min_days},
            "count": len(rows), "episodes": rows}
