"""E3 : charge de travail variable, « routine » contre « étude régionale » (prédiction : docs/e3_prediction.md).

Usage : uv run python -m bench.e3 --config local|citus2 [--n 200] [--reps 5]
Une série = n requêtes tirées avec une graine fixe (les mêmes pour toutes les configurations), envoyées une par
une par un seul client. La part de requêtes régionales varie : 0, 1, 5, 25, 50 et 100 %.
  routine  : F1 sur une station au hasard, fenêtre de 30 jours dans 2015-2024
  régionale: F2 et F3 en alternance, sur un pays entier, 2015-2024
Mesures : une série d'échauffement (non comptée), puis --reps répétitions ; temps total de la série (médiane,
IQR) et temps médian de chaque type de requête. Le point de basculement (part de régionales à partir de
laquelle le distribué gagne) se lit en comparant les deux fichiers de résultats (bench/report.py).
Résultats : bench/results/e3_<config>.json.
"""

import argparse
import random
import statistics
import time

from bench import common, workloads
from weatherscope.db import connect

SHARES = [0, 1, 5, 25, 50, 100]
SEED = 20261108


def build_series(ids: list[str], n: int, share: int) -> list[tuple[str, object]]:
    """Série reproductible : mêmes requêtes dans le même ordre pour une part donnée, quelle que soit la config."""
    rng = random.Random(SEED + share)
    n_regional = round(n * share / 100)
    kinds = ["G"] * n_regional + ["R"] * (n - n_regional)
    rng.shuffle(kinds)
    series, g = [], 0
    for kind in kinds:
        if kind == "R":
            series.append(("routine", workloads.routine_query(rng, ids)))
        else:
            series.append(("régionale", workloads.regional_query(g)))
            g += 1
    return series


def run_series(conn, series) -> tuple[float, dict[str, list[float]]]:
    per_type: dict[str, list[float]] = {"routine": [], "régionale": []}
    t0 = time.perf_counter()
    for kind, fn in series:
        t = time.perf_counter()
        fn(conn)
        per_type[kind].append(time.perf_counter() - t)
    return time.perf_counter() - t0, per_type


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, choices=["local", "citus2"])
    p.add_argument("--n", type=int, default=200, help="requêtes par série")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--shares", type=int, nargs="+", default=SHARES)
    args = p.parse_args()
    url = common.activate(args.config)
    out = {"config": args.config, "environment": common.environment(url),
           "protocol": {"queries_per_series": args.n, "repetitions": args.reps, "warmup_series": 1, "seed": SEED,
                        "shares_percent": args.shares, "client": "un seul client, requêtes séquentielles"},
           "series": {}}
    with connect(url) as conn:
        ids = workloads.station_ids(conn)
        for share in args.shares:
            series = build_series(ids, args.n, share)
            run_series(conn, series[: max(10, args.n // 10)])  # échauffement du cache
            totals, routine, regional = [], [], []
            for _ in range(args.reps):
                total, per_type = run_series(conn, series)
                totals.append(total)
                routine += per_type["routine"]
                regional += per_type["régionale"]
            entry = {"total": common.stats(totals), "queries_regional": len(regional) // args.reps,
                     "queries_routine": len(routine) // args.reps}
            if routine:
                entry["routine_median_s"] = round(statistics.median(routine), 5)
            if regional:
                entry["regional_median_s"] = round(statistics.median(regional), 4)
            out["series"][str(share)] = entry
            print(f"{args.config:7} {share:3d} % régionales : série {entry['total']['median_s']} s "
                  f"(IQR {entry['total']['iqr_s']}), routine {entry.get('routine_median_s')} s, "
                  f"régionale {entry.get('regional_median_s')} s")
            common.save(f"e3_{args.config}", out)  # sauvegarde au fil de l'eau (mesures longues)


if __name__ == "__main__":
    main()
