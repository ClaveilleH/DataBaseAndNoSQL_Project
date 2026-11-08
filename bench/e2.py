"""E2 : local contre distribué (Citus-2 et Citus-3) sur les mêmes données et les mêmes requêtes.

Usage : uv run python -m bench.e2 --config local|citus2|citus3 [--runs 7]
Données : le plus grand sous-ensemble de E1 (774 stations, 1991-2024, 21,46 M observations).
Un seul déploiement tourne à la fois (`common.activate`) avec le même budget de tampons total (~2 Go).
Requêtes (bench/workloads.py) : une étroite (F1), une agrégation longue, des analyses multi-stations (F2, F4) et F3.
Mesures : 1 exécution d'échauffement écartée (sa durée est notée : elle montre l'effet du cache), puis --runs
exécutions chronométrées ; médiane, écart interquartile, minimum et maximum. Chaque résultat est résumé par
une empreinte SHA-256 de sa sérialisation canonique : elle doit être identique pour les trois configurations.
Pour Citus, le plan (`EXPLAIN`) donne le nombre de tâches de la requête.
Ordre conseillé : local, citus2, puis citus3 (le passage à 3 workers rééquilibre les shards : deploy/citus/add_worker.sh).
Résultats : bench/results/e2_<config>.json.
"""

import argparse
import hashlib
import json

from bench import common, workloads
from weatherscope.db import connect
from weatherscope.services import f1_station


def digest(result) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()[:16]


def task_count(conn) -> int | None:
    """Nombre de tâches Citus de F1 (étroite) : 1 si une seule instance est contactée."""
    with conn.cursor() as cur:
        cur.execute("EXPLAIN " + f1_station.SQL_SUMMARY, {"station": workloads.STATION, "start": "2022-01-01",
                                                         "end": "2022-12-31"})
        for (line,) in cur.fetchall():
            if "Task Count" in line:
                return int(line.split(":")[1])
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, choices=["local", "citus2", "citus3"])
    p.add_argument("--runs", type=int, default=7)
    args = p.parse_args()
    url = common.activate(args.config)
    out = {"config": args.config, "environment": common.environment(url),
           "protocol": {"runs": args.runs, "warmup": 1, "cache": "chaud après 1 exécution d'échauffement ; "
                        "la durée de cette 1re exécution est notée (first_run_s)"},
           "queries": {}}
    if args.config != "local":
        out["placement"] = common.placement(url)
    with connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM observations")
            out["observations"] = cur.fetchone()[0]
        if args.config != "local":
            out["f1_task_count"] = task_count(conn)
        for label, fn in workloads.E2_QUERIES.items():
            runs = 3 if "F4" in label else args.runs  # F4 recalcule les quantiles de référence à chaque requête
            res = common.measure(lambda fn=fn: fn(conn), runs=runs)
            res["result_digest"] = digest(fn(conn))
            out["queries"][label] = res
            print(f"{args.config:7} {label} : médiane {res['median_s']} s (IQR {res['iqr_s']}), "
                  f"1re exécution {res['first_run_s']} s, empreinte {res['result_digest']}")
    common.save(f"e2_{args.config}", out)


if __name__ == "__main__":
    main()
