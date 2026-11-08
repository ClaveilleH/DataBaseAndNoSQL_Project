"""E1 : volume de données croissant, sur le serveur PostgreSQL local.

Usage : uv run python -m bench.e1 [--sizes 25 50 100] [--runs 5] [--keep] [--full-ingest-seconds S]
Trois sous-ensembles de l'archive réelle, chacun chargé dans sa propre base par le même chemin d'import
(ingest.load.import_files, 1991-2024 : la référence F3 est comprise) :
  25 %  : une station sur quatre (par ordre d'identifiant)
  50 %  : une station sur deux
  100 % : les 774 stations (au moins 10 millions d'observations brutes)
Pour chaque taille : observations, temps d'ingestion, espace disque (tables, index, base), temps des requêtes
de service représentatives, et taux de succès du cache (blocs lus en mémoire / total) pendant les requêtes,
pour dire si les données tiennent dans la mémoire de la base (shared_buffers).
Résultats : bench/results/e1.json. Le serveur local doit tourner ; aucune autre charge ne doit être active.
"""

import argparse
import os
import time

import psycopg

from bench import common, workloads
from ingest.load import import_files
from weatherscope.db import connect

ROOT = common.ROOT
ADMIN_URL = common.URLS["local"].rsplit("/", 1)[0] + "/postgres"
QUERIES = {k: v for k, v in workloads.E2_QUERIES.items() if "F4" not in k}  # F4 : voir E2


def database_url(name: str) -> str:
    return common.URLS["local"].rsplit("/", 1)[0] + "/" + name


def recreate_database(name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin, admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{name}"')
    with connect(database_url(name)) as conn:
        conn.execute((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        conn.commit()


def db_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT blks_hit, blks_read FROM pg_stat_database WHERE datname = current_database()")
        hit, read = cur.fetchone()
        return {"hit": hit, "read": read}


def sizes(conn) -> dict:
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        out["database_mb"] = cur.fetchone()[0] // 2**20
        for table in ("observations", "monthly_stats"):
            cur.execute("SELECT pg_total_relation_size(%s), pg_relation_size(%s), pg_indexes_size(%s)", (table,) * 3)
            total, heap, idx = cur.fetchone()
            out[table] = {"total_mb": total // 2**20, "table_mb": heap // 2**20, "index_mb": idx // 2**20}
        cur.execute("SELECT count(*), count(DISTINCT station), min(date), max(date) FROM observations")
        n, stations, first, last = cur.fetchone()
        out.update(observations_rows=n, stations=stations, first_date=first, last_date=last)
        cur.execute("SELECT count(*) FROM observations WHERE date >= '2015-01-01'")
        out["study_rows"] = cur.fetchone()[0]
        out["reference_rows"] = n - out["study_rows"]
    return out


def run_size(pct: int, runs: int, keep: bool, full_ingest_s: float | None = None) -> dict:
    """pct = 100 avec full_ingest_s : réutilise la base principale (chargement initial déjà fait, durée mesurée seul)."""
    reuse = pct == 100 and full_ingest_s is not None
    name = "weatherscope" if reuse else f"weatherscope_e1_{pct}"
    step = {25: 4, 50: 2, 100: 1}[pct]
    files = sorted((ROOT / "data" / "raw" / "by_station").glob("*.csv.gz"))[::step]
    print(f"== {pct} % : {len(files)} stations, base {name}" + (" (chargement initial réutilisé)" if reuse else ""))
    url = common.URLS["local"] if reuse else database_url(name)
    if not reuse:
        recreate_database(name)
    with connect(url) as conn:
        if reuse:
            ingest_s, counts = full_ingest_s, None
        else:
            t = time.perf_counter()
            counts = import_files(conn, files, (1991, 2024), log=lambda _: None)
            ingest_s = time.perf_counter() - t
            with conn.cursor() as cur:
                cur.execute("ANALYZE")
            conn.commit()
        result = {"pct": pct, "files": len(files), "ingest_s": round(ingest_s, 1), "import_counts": counts,
                  "ingest_source": "chargement initial de la base principale (mesuré sans autre charge)" if reuse
                  else "base dédiée, import_files", "size": sizes(conn)}
        n = result["size"]["observations_rows"]
        result["ingest_rows_per_s"] = round(n / ingest_s)
        print(f"   {n:,} observations en {ingest_s:.0f} s ({result['ingest_rows_per_s']:,} lignes/s), "
              f"base {result['size']['database_mb']} Mo")

        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('shared_buffers')")
            result["shared_buffers"] = cur.fetchone()[0]
        before = db_stats(conn)
        result["queries"] = {}
        for label, fn in QUERIES.items():
            result["queries"][label] = common.measure(lambda fn=fn: fn(conn), runs=runs)
            print(f"   {label} : médiane {result['queries'][label]['median_s']} s")
        after = db_stats(conn)
        hit, read = after["hit"] - before["hit"], after["read"] - before["read"]
        result["cache_hit_ratio"] = round(hit / (hit + read), 4) if hit + read else None
        # blocs « lus » = hors tampons PostgreSQL ; peuvent venir du cache du système, pas forcément du disque.
        result["blocks_outside_shared_buffers"] = read
    if not keep and not reuse:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", type=int, nargs="+", default=[25, 50, 100], choices=[25, 50, 100])
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--keep", action="store_true", help="ne pas supprimer les bases de test")
    p.add_argument("--full-ingest-seconds", type=float,
                   help="durée du chargement initial complet (base principale) : évite de recharger les 21 M lignes")
    args = p.parse_args()
    common.activate("local")
    out = {"environment": common.environment(common.URLS["local"]), "protocol": {
        "runs": args.runs, "warmup": 1, "cache": "chaud (1 exécution d'échauffement par requête)",
        "ingestion": "ingest.load.import_files, paquets de 50 fichiers, une transaction par paquet, 1991-2024"},
        "sizes": [run_size(pct, args.runs, args.keep, args.full_ingest_seconds) for pct in args.sizes]}
    common.save("e1", out)


if __name__ == "__main__":
    os.environ.setdefault("DATABASE_URL", common.URLS["local"])
    main()
