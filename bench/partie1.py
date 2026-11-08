"""Partie I : mesures sur la base locale (D26).

Usage : uv run python -m bench.partie1 [--runs 5]
1. Décision justifiée par une mesure : F3 sur monthly_stats contre F3 recalculé sur observations.
2. Conception alternative : table large observations_wide (sql/alt_wide.sql, une ligne par station et par jour)
   contre le modèle retenu (une ligne par mesure), sur trois requêtes ; taille et temps de construction.
Chaque requête : 1 exécution d'échauffement puis --runs exécutions chronométrées (cache chaud) ;
on vérifie que les deux versions comparées renvoient exactement les mêmes lignes.
Résultats : bench/results/partie1.json.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from weatherscope.db import connect
from weatherscope.services import f3_anomalies

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "results" / "partie1.json"
VALID = "qflag IS NULL AND mflag IS DISTINCT FROM 'P'"

# F3 sans agrégats : la CTE ms est recalculée depuis les observations journalières.
F3_RAW = f3_anomalies.SQL.replace(
    """    SELECT m.station, s.zone, s.cell_lat, s.cell_lon, m.year, m.month,
           m.sum_value::numeric / m.n_valid AS mean
    FROM monthly_stats m JOIN stations s ON s.id = m.station
    WHERE s.zone = ANY(%(zones)s) AND m.element = %(element)s AND m.n_valid > 0
      AND m.n_valid * 10 >= 8 * extract(day FROM make_date(m.year, m.month, 1) + interval '1 month - 1 day')
      AND (m.year BETWEEN 1991 AND 2020 OR m.year BETWEEN %(y0)s AND %(y1)s)""",
    f"""    SELECT o.station, s.zone, s.cell_lat, s.cell_lon,
           extract(year FROM o.date)::smallint AS year, extract(month FROM o.date)::smallint AS month,
           sum(o.value)::numeric / count(*) AS mean
    FROM observations o JOIN stations s ON s.id = o.station
    WHERE s.zone = ANY(%(zones)s) AND o.element = %(element)s AND o.{VALID.replace(' mflag', ' o.mflag')}
      AND (extract(year FROM o.date) BETWEEN 1991 AND 2020 OR extract(year FROM o.date) BETWEEN %(y0)s AND %(y1)s)
    GROUP BY 1, 2, 3, 4, 5, 6
    HAVING count(*) * 10 >= 8 * extract(day FROM make_date(extract(year FROM o.date)::smallint,
                                        extract(month FROM o.date)::smallint, 1) + interval '1 month - 1 day')""")
assert F3_RAW != f3_anomalies.SQL, "la CTE ms de F3 a changé : mettre à jour F3_RAW"
F3_PARAMS = {"zones": ["GM", "SP"], "element": "TMAX", "y0": 2015, "y1": 2024}

# Requêtes de comparaison long / large. Mêmes résultats attendus des deux côtés.
STATION = {"station": "SP000003195"}
LONG_WIDE = {
    "F1 : résumé mensuel d'une station sur 10 ans (3 éléments)": (
        f"""SELECT element, extract(year FROM date)::int y, extract(month FROM date)::int m,
                   count(*) FILTER (WHERE {VALID}) n, sum(value) FILTER (WHERE {VALID}) s
            FROM observations WHERE station = %(station)s AND date BETWEEN '2015-01-01' AND '2024-12-31'
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""",
        """SELECT e.element, extract(year FROM date)::int y, extract(month FROM date)::int m,
                  count(*) FILTER (WHERE e.v IS NOT NULL AND e.q IS NULL AND e.mf IS DISTINCT FROM 'P') n,
                  sum(e.v) FILTER (WHERE e.q IS NULL AND e.mf IS DISTINCT FROM 'P') s
           FROM observations_wide w,
                LATERAL (VALUES ('PRCP', prcp, prcp_qflag, prcp_mflag), ('TMAX', tmax, tmax_qflag, tmax_mflag),
                                ('TMIN', tmin, tmin_qflag, tmin_mflag)) e(element, v, q, mf)
           WHERE station = %(station)s AND date BETWEEN '2015-01-01' AND '2024-12-31'
           GROUP BY 1, 2, 3 HAVING count(*) FILTER (WHERE e.v IS NOT NULL) > 0 ORDER BY 1, 2, 3""",
        STATION),
    "F2 : épisodes TMAX >= 40 °C en Espagne, 2015-2024": (
        f"""WITH d AS (SELECT o.station, o.date FROM observations o JOIN stations s ON s.id = o.station
                       WHERE s.zone = 'SP' AND o.element = 'TMAX' AND o.{VALID.replace(' mflag', ' o.mflag')}
                         AND o.value >= 400 AND o.date BETWEEN '2015-01-01' AND '2024-12-31')
            SELECT station, min(date), max(date), count(*) FROM
              (SELECT station, date, date - (row_number() OVER (PARTITION BY station ORDER BY date))::int g FROM d) r
            GROUP BY station, g HAVING count(*) >= 3 ORDER BY 1, 2""",
        """WITH d AS (SELECT w.station, w.date FROM observations_wide w JOIN stations s ON s.id = w.station
                      WHERE s.zone = 'SP' AND w.tmax_qflag IS NULL AND w.tmax >= 400
                        AND w.date BETWEEN '2015-01-01' AND '2024-12-31')
           SELECT station, min(date), max(date), count(*) FROM
             (SELECT station, date, date - (row_number() OVER (PARTITION BY station ORDER BY date))::int g FROM d) r
           GROUP BY station, g HAVING count(*) >= 3 ORDER BY 1, 2""",
        {}),
    "Amplitude TMAX - TMIN > 20 °C le même jour, Espagne 2015-2024 (par station)": (
        """SELECT x.station, count(*) FROM observations x
           JOIN observations n ON n.station = x.station AND n.date = x.date AND n.element = 'TMIN'
           JOIN stations s ON s.id = x.station
           WHERE s.zone = 'SP' AND x.element = 'TMAX' AND x.qflag IS NULL AND n.qflag IS NULL
             AND x.date BETWEEN '2015-01-01' AND '2024-12-31' AND x.value - n.value > 200
           GROUP BY 1 ORDER BY 1""",
        """SELECT w.station, count(*) FROM observations_wide w JOIN stations s ON s.id = w.station
           WHERE s.zone = 'SP' AND w.tmax_qflag IS NULL AND w.tmin_qflag IS NULL
             AND w.date BETWEEN '2015-01-01' AND '2024-12-31' AND w.tmax - w.tmin > 200
           GROUP BY 1 ORDER BY 1""",
        {}),
}


def timed(conn, sql: str, params: dict, runs: int) -> tuple[list, dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)  # échauffement
        rows = cur.fetchall()
        times = []
        for _ in range(runs):
            t = time.perf_counter()
            cur.execute(sql, params)
            cur.fetchall()
            times.append(time.perf_counter() - t)
    return rows, {"median_s": round(statistics.median(times), 4), "min_s": round(min(times), 4),
                  "max_s": round(max(times), 4), "runs": runs}


def size(conn, table: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_total_relation_size(%s), pg_relation_size(%s), pg_indexes_size(%s), "
                    "(SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass)", (table,) * 4)
        total, heap, idx, rows = cur.fetchone()
    return {"rows": rows, "total_mb": total // 2**20, "table_mb": heap // 2**20, "index_mb": idx // 2**20}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5)
    runs = p.parse_args().runs
    result = {"runs": runs, "cache": "chaud (1 exécution d'échauffement)"}

    with connect() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT version(), current_setting('shared_buffers'), "
                        "current_setting('max_parallel_workers_per_gather')")
            result["server"] = dict(zip(("version", "shared_buffers", "parallel_workers"), cur.fetchone(),
                                        strict=True))

        print("1. F3 : agrégats mensuels contre observations brutes")
        a, ta = timed(conn, f3_anomalies.SQL, F3_PARAMS, runs)
        b, tb = timed(conn, F3_RAW, F3_PARAMS, runs)
        same = sorted(a) == sorted(b)
        result["f3"] = {"monthly_stats": ta, "observations": tb, "identical": same, "rows": len(a)}
        print(f"   monthly_stats {ta['median_s']} s, observations {tb['median_s']} s, identiques : {same}")

        print("2. Conception alternative : table large")
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS observations_wide")
            t = time.perf_counter()
            cur.execute((ROOT / "sql" / "alt_wide.sql").read_text())
            build = time.perf_counter() - t
            cur.execute("ANALYZE observations_wide")
        result["wide"] = {"build_s": round(build, 1), "size": size(conn, "observations_wide"),
                          "long_size": size(conn, "observations"), "queries": {}}
        print(f"   construite en {build:.0f} s ; {result['wide']['size']} contre {result['wide']['long_size']}")
        for name, (q_long, q_wide, params) in LONG_WIDE.items():
            a, ta = timed(conn, q_long, params, runs)
            b, tb = timed(conn, q_wide, params, runs)
            same = sorted(a) == sorted(b)
            result["wide"]["queries"][name] = {"long": ta, "wide": tb, "identical": same, "rows": len(a)}
            print(f"   {name} : long {ta['median_s']} s, large {tb['median_s']} s, identiques : {same}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
