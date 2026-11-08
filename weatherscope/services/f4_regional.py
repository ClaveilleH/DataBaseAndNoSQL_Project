"""F4 — Événements régionaux : plusieurs mailles touchées en même temps (définition D22).

- Jour inhabituel pour une station : valeur valide strictement au-dessus de son quantile (95 % par défaut)
  pour ce mois calendaire, calculé sur 1991-2020 (au moins 80 % des jours de référence disponibles).
- La densité de stations n'est pas uniforme : on compte des mailles de 0,5°, pas des stations.
  Pour chaque jour : mailles qui rapportent (au moins une station valide) et mailles touchées
  (au moins une station inhabituelle).
- Jour régional : au moins --min-cells mailles touchées et au moins --min-share de celles qui rapportent.
  Les jours régionaux consécutifs forment un événement.
- Sévérité d'un événement : somme, sur ses jours, de la part des mailles touchées (« jours-zone »).
- Extrême isolé : jour où une seule maille est touchée.
Preuves : pour chaque événement, les observations inhabituelles (station, date, valeur, seuil).
"""

from datetime import date, timedelta
from fractions import Fraction

from weatherscope.services.common import (
    REFERENCE,
    UNITS,
    VALID,
    Area,
    fetch,
    round2,
    unit_value,
)

# 1. Seuils par station et mois calendaire, calculés une seule fois par requête F4 (le plus coûteux :
#    30 ans de mesures). Regroupés par station (colonne de distribution) : en distribué, chaque worker
#    calcule seul les seuils de ses stations ; le coordinateur ne reçoit qu'une ligne par station et par mois.
SQL_THRESHOLDS = f"""
SELECT o.station, extract(month FROM o.date)::int AS month,
       percentile_disc(%(quantile)s) WITHIN GROUP (ORDER BY o.value) AS p
FROM observations o JOIN stations s ON s.id = o.station
WHERE {{area}} AND o.element = %(element)s AND {VALID}
  AND o.date BETWEEN '{REFERENCE[0]}-01-01' AND '{REFERENCE[1]}-12-31'
GROUP BY 1, 2
-- au moins 80 pour cent des jours de ce mois calendaire sur les 30 ans (février compté à 28 jours)
HAVING count(*) * 10 >= 8 * 30 * extract(day FROM make_date(2001, extract(month FROM o.date)::int, 1)
                                         + interval '1 month - 1 day')
ORDER BY 1, 2
"""

# 2. Observations de la période avec le seuil de leur station : les seuils sont passés en paramètres
#    (tableaux), que Citus envoie à chaque worker ; la jointure se fait donc sur les workers.
OBS = f"""obs AS (
    SELECT o.station, o.date, o.value, t.p, s.cell_lat, s.cell_lon
    FROM observations o
    JOIN stations s ON s.id = o.station
    JOIN unnest(%(thr_station)s::text[], %(thr_month)s::int[], %(thr_p)s::int[]) AS t(station, month, p)
      ON t.station = o.station AND t.month = extract(month FROM o.date)
    WHERE o.element = %(element)s AND o.date BETWEEN %(start)s AND %(end)s AND {VALID}
)"""

SQL_DAILY = f"""
WITH {OBS},
cell_day AS (
    SELECT date, cell_lat, cell_lon,
           bool_or(value > p) AS hit,
           count(*) FILTER (WHERE value > p) AS stations_hit,
           coalesce(sum(value - p) FILTER (WHERE value > p), 0) AS excess
    FROM obs GROUP BY 1, 2, 3
)
SELECT date, count(*) AS cells_reporting, count(*) FILTER (WHERE hit) AS cells_hit,
       sum(stations_hit) AS stations_hit, sum(excess) AS excess
FROM cell_day
GROUP BY date
HAVING bool_or(hit)
ORDER BY date
"""

SQL_EVIDENCE = f"""
WITH {OBS}
SELECT station, date, value, p AS threshold, cell_lat, cell_lon
FROM obs WHERE value > p AND date = ANY(%(dates)s)
ORDER BY date, station
"""


def params_for(area: Area, element: str, start: date, end: date, quantile: float) -> tuple[str, dict]:
    where, params = area.sql()
    return where, {**params, "element": element, "start": start, "end": end, "quantile": quantile}


def with_thresholds(conn, area: Area, element: str, start: date, end: date, quantile: float) -> dict:
    """Paramètres de SQL_DAILY et SQL_EVIDENCE : calcule les seuils (SQL_THRESHOLDS) et les ajoute en tableaux."""
    where, params = params_for(area, element, start, end, quantile)
    thr = fetch(conn, SQL_THRESHOLDS.format(area=where), params)
    return {**params, "thr_station": [t["station"] for t in thr], "thr_month": [t["month"] for t in thr],
            "thr_p": [t["p"] for t in thr]}


def events(conn, area: Area, element: str, start: date, end: date, quantile: float = 0.95,
           min_cells: int = 3, min_share: float = 0.25, evidence: bool = True) -> dict:
    params = with_thresholds(conn, area, element, start, end, quantile)
    share_min = Fraction(str(min_share))
    days = fetch(conn, SQL_DAILY, params)

    regional = [d for d in days if d["cells_hit"] >= min_cells
                and Fraction(d["cells_hit"], d["cells_reporting"]) >= share_min]
    isolated = [d for d in days if d["cells_hit"] == 1]

    # Jours régionaux consécutifs -> événements.
    found, run = [], []
    for d in regional + [None]:
        if run and (d is None or d["date"] - run[-1]["date"] != timedelta(days=1)):
            shares = [Fraction(x["cells_hit"], x["cells_reporting"]) for x in run]
            peak = max(run, key=lambda x: (Fraction(x["cells_hit"], x["cells_reporting"]), x["cells_hit"]))
            found.append({
                "start": run[0]["date"].isoformat(), "end": run[-1]["date"].isoformat(), "days": len(run),
                "severity": round2(sum(shares)), "peak_date": peak["date"].isoformat(),
                "peak_share": round2(max(shares)), "peak_cells_hit": peak["cells_hit"],
                "stations_hit": int(sum(x["stations_hit"] for x in run)),
                "dates": [x["date"] for x in run],
            })
            run = []
        if d is not None:
            run.append(d)
    found.sort(key=lambda e: (-e["severity"], e["start"]))

    top_isolated = sorted(isolated, key=lambda d: (-d["excess"], d["date"]))[:10]
    isolated_top = [{"date": d["date"].isoformat(), "cells_reporting": d["cells_reporting"],
                     "stations_hit": int(d["stations_hit"]), "excess": unit_value(int(d["excess"])),
                     "dates": [d["date"]]} for d in top_isolated]

    if evidence:
        wanted = [x for e in found + isolated_top for x in e["dates"]]
        ev = fetch(conn, SQL_EVIDENCE, {**params, "dates": wanted}) if wanted else []
        by_date: dict[date, list] = {}
        for r in ev:
            by_date.setdefault(r["date"], []).append({
                "station": r["station"], "date": r["date"].isoformat(), "value": unit_value(r["value"]),
                "threshold": unit_value(r["threshold"]), "cell": [float(r["cell_lat"]), float(r["cell_lon"])]})
        for e in found + isolated_top:
            e["evidence"] = [x for d in e["dates"] for x in by_date.get(d, [])]
    for e in found + isolated_top:
        e.pop("dates")

    return {"service": "F4", "unit": UNITS[element],
            "params": {**area.describe(), "element": element, "start": start.isoformat(), "end": end.isoformat(),
                       "quantile": quantile, "min_cells": min_cells, "min_share": min_share,
                       "reference": list(REFERENCE)},
            "count": len(found), "events": found,
            "isolated": {"days": len(isolated), "top": isolated_top}}
