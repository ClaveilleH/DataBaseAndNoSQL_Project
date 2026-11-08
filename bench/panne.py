"""Perte d'une instance : arrêt d'un worker Citus, puis F1 (station du worker arrêté, puis d'un autre) et F3.

Usage : uv run python -m bench.panne [--worker w2]
Le sujet demande de montrer ce que reçoit l'utilisateur : on lance donc la vraie interface en ligne de commande
(weatherscope.cli) et on enregistre son code de sortie et son message. Une réponse partielle ne doit jamais être
présentée comme complète : la commande doit échouer explicitement (code 2, « ÉCHEC », aucun résultat).
Étapes : (1) référence avant panne ; (2) `docker compose stop <worker>` ; (3) F1 sur une station du worker arrêté,
F1 sur une station d'un autre worker, F3 ; (4) redémarrage du worker et vérification que les résultats sont
identiques à ceux d'avant la panne (empreintes SHA-256 de la sortie JSON).
Limite : replication_factor = 1, donc les stations du worker arrêté restent indisponibles jusqu'à son redémarrage ;
un système répliqué pourrait répondre depuis une copie (voir le rapport).
Résultats : bench/results/panne.json.
"""

import argparse
import hashlib
import os
import subprocess
import sys
import time

from bench import common
from weatherscope.db import connect

CLI = [sys.executable, "-m", "weatherscope.cli"]
PERIOD = ["--start", "2015-01-01", "--end", "2024-12-31"]


def station_of(url: str, worker: str) -> str:
    """Une station (avec TMAX récent) dont les mesures sont sur `worker`, d'après le placement réel des shards."""
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT shardid FROM citus_shards WHERE table_name = 'observations'::regclass AND nodename = %s",
                    (worker,))
        shards = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT id, get_shard_id_for_distribution_column('observations', id) FROM stations ORDER BY id")
        ids = [sid for sid, shard in cur.fetchall() if shard in shards]
        for sid in ids[5:]:
            cur.execute("SELECT 1 FROM observations WHERE station = %s AND element = 'TMAX' AND date >= '2015-01-01' "
                        "LIMIT 1", (sid,))
            if cur.fetchone():
                return sid
    raise RuntimeError(f"aucune station utilisable sur {worker}")


def run_cli(args: list[str]) -> dict:
    t = time.perf_counter()
    proc = subprocess.run(CLI + args, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return {"command": "weatherscope.cli " + " ".join(args), "exit_code": proc.returncode,
            "seconds": round(time.perf_counter() - t, 2),
            "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest()[:16],
            "message": " ".join(proc.stdout.split())[:400] if proc.returncode else "(résultat complet affiché)"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--worker", default="w2")
    worker = p.parse_args().worker
    url = common.activate("citus2")
    others = [w for w in common.WORKERS["citus2"] if w != worker]
    st_down, st_up = station_of(url, worker), station_of(url, others[0])
    f1 = lambda sid: ["station", sid, *PERIOD, "--json"]  # noqa: E731
    f3 = ["anomalies", "-z", "GM", "-z", "SP", "--json"]

    out = {"environment": common.environment(url), "stopped_worker": worker,
           "station_on_stopped_worker": st_down, "station_on_other_worker": st_up, "steps": {}}
    out["steps"]["avant_panne"] = {"F1 station du worker arrêté": run_cli(f1(st_down)),
                                   "F1 autre station": run_cli(f1(st_up)), "F3": run_cli(f3)}
    common.sh(common.CITUS_COMPOSE + ["stop", worker])
    time.sleep(3)
    out["steps"]["worker_arrete"] = {"F1 station du worker arrêté": run_cli(f1(st_down)),
                                     "F1 autre station": run_cli(f1(st_up)), "F3": run_cli(f3)}
    common.sh(common.CITUS_COMPOSE + ["start", worker])
    common.wait_ready(url, True)
    time.sleep(10)
    out["steps"]["apres_redemarrage"] = {"F1 station du worker arrêté": run_cli(f1(st_down)),
                                         "F1 autre station": run_cli(f1(st_up)), "F3": run_cli(f3)}
    before, down, after = (out["steps"][k] for k in ("avant_panne", "worker_arrete", "apres_redemarrage"))
    out["checks"] = {
        "F1 sur le worker arrêté échoue explicitement (code 2)": down["F1 station du worker arrêté"]["exit_code"] == 2,
        "F1 sur un autre worker répond normalement": down["F1 autre station"]["exit_code"] == 0
        and down["F1 autre station"]["stdout_sha256"] == before["F1 autre station"]["stdout_sha256"],
        "F3 échoue explicitement (code 2)": down["F3"]["exit_code"] == 2,
        "aucun résultat partiel pour F1 et F3 pendant la panne": all(
            down[k]["message"] != "(résultat complet affiché)" for k in ("F1 station du worker arrêté", "F3")),
        "après redémarrage, F1 et F3 identiques à avant la panne": all(
            after[k]["stdout_sha256"] == before[k]["stdout_sha256"] and after[k]["exit_code"] == 0 for k in before),
    }
    for k, v in out["checks"].items():
        print(("OK    " if v else "ÉCHEC ") + k)
    common.save("panne", out)
    sys.exit(0 if all(out["checks"].values()) else 1)


if __name__ == "__main__":
    main()
