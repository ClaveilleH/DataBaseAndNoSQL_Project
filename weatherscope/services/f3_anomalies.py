"""F3 — Mois anormaux : écart à la normale 1991-2020, par zone, classé (définition D17).

À partir de monthly_stats (sommes et comptes entiers, tenus à jour par F5) :
- mois-station éligible : au moins 80 % des jours du mois ont une observation valide ;
  valeur du mois = moyenne journalière (°C pour TMAX/TMIN, mm/jour pour PRCP) ;
- normale station x mois calendaire : moyenne des mois éligibles de 1991-2020, si au moins 24 années ;
- anomalie de zone : moyenne par maille de 0,5° des anomalies des stations, puis moyenne des mailles,
  pour ne pas surpondérer les régions denses ; au moins 5 mailles.
Classement par |anomalie| décroissante, puis zone, année, mois.
"""

from weatherscope.services.common import REFERENCE, UNITS, fetch, round2

MIN_REF_YEARS = 24
MIN_CELLS = 5

SQL = f"""
WITH ms AS (
    SELECT m.station, s.zone, s.cell_lat, s.cell_lon, m.year, m.month,
           m.sum_value::numeric / m.n_valid AS mean
    FROM monthly_stats m JOIN stations s ON s.id = m.station
    WHERE s.zone = ANY(%(zones)s) AND m.element = %(element)s AND m.n_valid > 0
      AND m.n_valid * 10 >= 8 * extract(day FROM make_date(m.year, m.month, 1) + interval '1 month - 1 day')
      AND (m.year BETWEEN {REFERENCE[0]} AND {REFERENCE[1]} OR m.year BETWEEN %(y0)s AND %(y1)s)
), normal AS (
    SELECT station, month, avg(mean) AS normal
    FROM ms WHERE year BETWEEN {REFERENCE[0]} AND {REFERENCE[1]}
    GROUP BY station, month HAVING count(*) >= {MIN_REF_YEARS}
), cells AS (
    SELECT ms.zone, ms.year, ms.month, ms.cell_lat, ms.cell_lon,
           avg(ms.mean - n.normal) AS anomaly, count(*) AS stations
    FROM ms JOIN normal n ON n.station = ms.station AND n.month = ms.month
    WHERE ms.year BETWEEN %(y0)s AND %(y1)s
    GROUP BY 1, 2, 3, 4, 5
)
SELECT zone, year, month, avg(anomaly) AS anomaly, count(*) AS cells, sum(stations) AS stations
FROM cells
GROUP BY zone, year, month
HAVING count(*) >= {MIN_CELLS}
"""


def query(zones: list[str], element: str, y0: int, y1: int) -> tuple[str, dict]:
    return SQL, {"zones": zones, "element": element, "y0": y0, "y1": y1}


def anomalies(conn, zones: list[str], element: str, y0: int, y1: int) -> dict:
    sql, params = query(zones, element, y0, y1)
    rows = [{
        "zone": r["zone"], "year": r["year"], "month": r["month"],
        "anomaly": round2(r["anomaly"] / 10),  # dixièmes -> °C ou mm/jour
        "cells": r["cells"], "stations": int(r["stations"]),
        "sources": {"zone": r["zone"], "element": element, "year": r["year"], "month": r["month"]},
    } for r in fetch(conn, sql, params)]
    rows.sort(key=lambda r: (-abs(r["anomaly"]), r["zone"], r["year"], r["month"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    unit = UNITS[element] + ("/jour" if element == "PRCP" else "")
    return {"service": "F3", "unit": unit,
            "params": {"zones": zones, "element": element, "years": [y0, y1], "reference": list(REFERENCE)},
            "months": rows}
