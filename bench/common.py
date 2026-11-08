"""Outils communs aux expériences E1-E4 : déploiements, mesures statistiques, description de l'environnement.

Un seul déploiement tourne à la fois (le poste n'a que 13 Go de RAM) : `activate()` arrête les autres,
démarre celui qui est demandé avec le même budget mémoire total, et attend qu'il réponde.
  local  : un PostgreSQL 17.2, shared_buffers = 2 Go                       (deploy/local)
  citus2 : coordinateur (256 Mo) + 2 workers de 1 Go, soit 2 Go de tampons  (deploy/citus)
  citus3 : coordinateur (256 Mo) + 3 workers de 700 Mo, soit 2,1 Go          (deploy/citus, profil citus3)
"""

import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

from weatherscope.db import connect

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent / "results"
LOCAL_COMPOSE = ["docker", "compose", "-f", str(ROOT / "deploy" / "local" / "compose.yml")]
CITUS_COMPOSE = ["docker", "compose", "-f", str(ROOT / "deploy" / "citus" / "compose.yml"), "--profile", "citus3"]
# 127.0.0.1 et non localhost : sur Windows, « localhost » tente d'abord ::1 et met ~200 s à se connecter aux ports Docker.
URLS = {
    "local": "postgresql://weatherscope:weatherscope@127.0.0.1:5440/weatherscope",
    "citus2": "postgresql://weatherscope:weatherscope@127.0.0.1:5441/weatherscope",
    "citus3": "postgresql://weatherscope:weatherscope@127.0.0.1:5441/weatherscope",
}
WORKER_BUFFERS = {"citus2": "1GB", "citus3": "700MB"}
WORKERS = {"citus2": ["w1", "w2"], "citus3": ["w1", "w2", "w3"]}


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=kw.pop("check", True), **kw)


def wait_ready(url: str, citus: bool, timeout: float = 600) -> None:
    """Attend le serveur ; pour Citus, attend aussi que CHAQUE worker accepte les connexions
    (un worker recréé peut rester plusieurs minutes en récupération après un rééquilibrage)."""
    deadline = time.time() + timeout
    while True:
        try:
            with connect(url) as conn, conn.cursor() as cur:
                cur.execute("SELECT citus_version()" if citus else "SELECT 1")
                if citus:
                    cur.execute("SELECT bool_and(success) FROM run_command_on_workers($$SELECT 1$$)")
                    if not cur.fetchone()[0]:
                        raise RuntimeError("un worker n'accepte pas encore les connexions")
                return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(2)


def activate(config: str) -> str:
    """Arrête les autres déploiements, démarre `config`, renvoie son URL (DATABASE_URL à utiliser)."""
    if config == "local":
        sh(CITUS_COMPOSE + ["stop"])
        sh(LOCAL_COMPOSE + ["up", "-d"])
    else:
        sh(LOCAL_COMPOSE + ["stop"])
        env = {**os.environ, "WORKER_SHARED_BUFFERS": WORKER_BUFFERS[config]}
        services = ["coordinator", *WORKERS[config]]
        sh(CITUS_COMPOSE + ["up", "-d", "--force-recreate", *services], env=env)
        for extra in {"w3"} - set(WORKERS[config]):
            sh(CITUS_COMPOSE + ["stop", extra])
    wait_ready(URLS[config], config != "local")
    if config != "local":
        time.sleep(3)  # laisse le coordinateur rouvrir ses connexions vers les workers
    os.environ["DATABASE_URL"] = URLS[config]
    return URLS[config]


def stats(times: list[float]) -> dict:
    """Tendance centrale et variabilité d'une série de temps (secondes)."""
    q = statistics.quantiles(times, n=4, method="inclusive") if len(times) > 1 else [times[0]] * 3
    return {"runs": len(times), "median_s": round(statistics.median(times), 4), "mean_s": round(statistics.mean(times), 4),
            "stdev_s": round(statistics.stdev(times), 4) if len(times) > 1 else 0.0,
            "iqr_s": round(q[2] - q[0], 4), "min_s": round(min(times), 4), "max_s": round(max(times), 4),
            "all_s": [round(t, 4) for t in times]}


def measure(fn, runs: int = 7, warmup: int = 1) -> dict:
    """`warmup` exécutions écartées (cache chaud), puis `runs` exécutions chronométrées ; la 1re (froide) est notée."""
    cold = None
    for i in range(warmup):
        t = time.perf_counter()
        fn()
        cold = cold if cold is not None else time.perf_counter() - t
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return {**stats(times), "first_run_s": None if cold is None else round(cold, 4), "warmup_runs": warmup}


def environment(url: str | None = None) -> dict:
    """Versions matérielles et logicielles, et paramètres mémoire des instances (exigés par le sujet)."""
    info = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "os": platform.platform(), "python": sys.version.split()[0],
            "cpu_threads": os.cpu_count()}
    try:
        info["docker"] = sh(["docker", "version", "--format", "{{.Server.Version}}"]).stdout.strip()
        ncpu, mem = sh(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"]).stdout.split()
        info["docker_cpus"], info["docker_mem_gb"] = int(ncpu), round(int(mem) / 2**30, 1)
    except Exception:
        pass
    if url:
        with connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT version(), current_setting('shared_buffers'), current_setting('work_mem'), "
                        "current_setting('max_parallel_workers_per_gather')")
            v, sb, wm, par = cur.fetchone()
            info["server"] = {"postgres": v.split(" on ")[0], "shared_buffers": sb, "work_mem": wm, "parallel_workers": par}
            try:
                cur.execute("SELECT citus_version()")
                info["server"]["citus"] = cur.fetchone()[0].split(" on ")[0]
                cur.execute("SELECT nodename FROM pg_dist_node WHERE noderole = 'primary' ORDER BY nodeid")
                info["workers"] = [r[0] for r in cur.fetchall()]
            except Exception:
                conn.rollback()
    return info


def save(name: str, data: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"-> {path.relative_to(ROOT)}")
    return path


def placement(url: str) -> list[dict]:
    """Lignes et taille des mesures par worker (Citus) : équilibre des données."""
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute("""SELECT cs.nodename, count(*) AS shards, sum(cs.shard_size) AS bytes
                       FROM citus_shards cs WHERE cs.table_name = 'observations'::regclass
                       GROUP BY 1 ORDER BY 1""")
        return [{"worker": n, "shards": s, "observations_mb": round(b / 2**20, 1)} for n, s, b in cur.fetchall()]
