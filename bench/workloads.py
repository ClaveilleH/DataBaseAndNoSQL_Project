"""Requêtes représentatives de WeatherScope pour les expériences E1-E4.

Chaque requête est une fonction `fn(conn)` qui exécute un vrai service (ou la requête SQL de l'agrégation) :
  étroite        F1, une station, un an                              (examen courant : 1 shard en Citus)
  agrégation     moyenne annuelle de TMAX par zone, 1991-2024        (longue période, tous les shards)
  multi-stations F2 (épisodes de chaleur sur un pays entier, 10 ans) et F4 (événements régionaux)
  anomalies      F3 (mois anormaux, deux pays, sur monthly_stats)
Les paramètres sont fixes (reproductibles) ; E3 tire les stations et les fenêtres avec une graine.
"""

import random
from datetime import date, timedelta

from weatherscope.services import f1_station, f2_episodes, f3_anomalies, f4_regional
from weatherscope.services.common import VALID, Area, fetch, tenths

STATION = "SP000003195"  # Madrid / Retiro : série longue et complète
STUDY = (date(2015, 1, 1), date(2024, 12, 31))

SQL_YEARLY = f"""
SELECT s.zone, extract(year FROM o.date)::int AS year, count(*) AS n, sum(o.value) AS total
FROM observations o JOIN stations s ON s.id = o.station
WHERE o.element = 'TMAX' AND {VALID}
GROUP BY 1, 2 ORDER BY 1, 2"""


def narrow(conn):
    return f1_station.summary(conn, STATION, date(2022, 1, 1), date(2022, 12, 31))


def long_aggregation(conn):
    return fetch(conn, SQL_YEARLY, {})


def episodes_germany(conn):
    return f2_episodes.episodes(conn, Area(zones=["GM"]), "TMAX", *STUDY, tenths(30.0), 3)


def episodes_spain(conn):
    return f2_episodes.episodes(conn, Area(zones=["SP"]), "TMAX", *STUDY, tenths(35.0), 3)


def anomalies(conn):
    return f3_anomalies.anomalies(conn, ["GM", "SP"], "TMAX", 2015, 2024)


def regional_events(conn):
    return f4_regional.events(conn, Area(zones=["SP"]), "PRCP", *STUDY)


E2_QUERIES = {
    "étroite : F1, une station, un an": narrow,
    "agrégation longue : TMAX annuel par zone, 1991-2024": long_aggregation,
    "multi-stations : F2, Allemagne, TMAX >= 30 °C, 10 ans": episodes_germany,
    "multi-stations : F2, Espagne, TMAX >= 35 °C, 10 ans": episodes_spain,
    "anomalies : F3, deux pays, TMAX": anomalies,
    "multi-stations : F4, Espagne, PRCP, 10 ans": regional_events,
}


def station_ids(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM stations ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def routine_query(rng: random.Random, ids: list[str]):
    """Charge « routine » : F1 sur une station au hasard et une fenêtre de 30 jours dans 2015-2024."""
    sid = rng.choice(ids)
    start = STUDY[0] + timedelta(days=rng.randrange((STUDY[1] - STUDY[0]).days - 30))
    return lambda conn: f1_station.summary(conn, sid, start, start + timedelta(days=30))


def regional_query(k: int):
    """Charge « étude régionale » : F2 et F3 en alternance, sur un pays entier, 2015-2024."""
    if k % 2 == 0:
        zone, thr = (["GM"], 30.0) if (k // 2) % 2 == 0 else (["SP"], 35.0)
        return lambda conn: f2_episodes.episodes(conn, Area(zones=zone), "TMAX", *STUDY, tenths(thr), 3)
    zones = ["GM"] if (k // 2) % 2 == 0 else ["SP"]
    return lambda conn: f3_anomalies.anomalies(conn, zones, "TMAX", 2015, 2024)
