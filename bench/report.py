"""Tableaux Markdown (pour le rapport) à partir des résultats bruts de bench/results/*.json.

Usage : uv run python -m bench.report
Ne recalcule rien : lit les mesures de E1, E2, E3, E4 et de la panne, vérifie que les résultats des trois
configurations sont identiques (empreintes de E2) et confronte E3 à la prédiction de docs/e3_prediction.md.
"""

import json

from bench.common import RESULTS


def load(name: str) -> dict | None:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def table(header: list[str], rows: list[list]) -> None:
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join("---" for _ in header) + "|")
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")
    print()


def e1() -> None:
    d = load("e1")
    if not d:
        return
    print("## E1 : volume croissant (PostgreSQL local)\n")
    env = d["environment"]
    print(f"Serveur : {env['server']['postgres']}, shared_buffers {env['server']['shared_buffers']}, "
          f"Docker {env.get('docker_cpus')} CPU / {env.get('docker_mem_gb')} Go.\n")
    sizes = d["sizes"]
    table(["Part des stations", "Stations", "Observations", "dont référence", "Ingestion (s)", "lignes/s",
           "Base (Mo)", "Table observations (Mo)", "Cache hit"],
          [[f"{s['pct']} %", s["size"]["stations"], f"{s['size']['observations_rows']:,}", f"{s['size']['reference_rows']:,}",
            s["ingest_s"], f"{s['ingest_rows_per_s']:,}", s["size"]["database_mb"], s["size"]["observations"]["total_mb"],
            s["cache_hit_ratio"]] for s in sizes])
    labels = list(sizes[0]["queries"])
    table(["Requête (médiane, s)"] + [f"{s['pct']} %" for s in sizes],
          [[lab] + [f"{s['queries'][lab]['median_s']} (IQR {s['queries'][lab]['iqr_s']})" for s in sizes] for lab in labels])


def e2() -> None:
    runs = {c: load(f"e2_{c}") for c in ("local", "citus2", "citus3")}
    runs = {c: d for c, d in runs.items() if d}
    if not runs:
        return
    print("## E2 : local contre distribué\n")
    for c, d in runs.items():
        env = d["environment"]
        extra = f", workers {env.get('workers')}" if env.get("workers") else ""
        print(f"- {c} : {d['observations']:,} observations, {env['server']['postgres']}, "
              f"shared_buffers {env['server']['shared_buffers']}{extra}")
    print()
    labels = list(next(iter(runs.values()))["queries"])
    table(["Requête (médiane s, IQR)"] + list(runs),
          [[lab] + [f"{d['queries'][lab]['median_s']} (IQR {d['queries'][lab]['iqr_s']})" for d in runs.values()] for lab in labels])
    table(["Première exécution (s)"] + list(runs),
          [[lab] + [d["queries"][lab]["first_run_s"] for d in runs.values()] for lab in labels])
    same = {lab: len({d["queries"][lab]["result_digest"] for d in runs.values()}) == 1 for lab in labels}
    print("Résultats identiques entre configurations (empreinte SHA-256) :",
          "OUI pour toutes les requêtes" if all(same.values()) else f"NON : {[k for k, v in same.items() if not v]}", "\n")
    for c, d in runs.items():
        if "f1_task_count" in d:
            print(f"- {c} : F1 (une station) = {d['f1_task_count']} tâche(s) ; répartition {d['placement']}")
    print()


def e3() -> None:
    a, b = load("e3_local"), load("e3_citus2")
    if not (a and b):
        return
    print("## E3 : charge variable (temps total d'une série, médiane de "
          f"{a['protocol']['repetitions']} répétitions, {a['protocol']['queries_per_series']} requêtes)\n")
    rows, crossover = [], None
    for share in sorted(a["series"], key=int):
        if share not in b["series"]:
            continue
        la, ca = a["series"][share], b["series"][share]
        ratio = ca["total"]["median_s"] / la["total"]["median_s"]
        winner = "local" if ratio > 1 else "Citus-2"
        if winner == "Citus-2" and crossover is None:
            crossover = share
        rows.append([f"{share} %", f"{la['total']['median_s']} (IQR {la['total']['iqr_s']})",
                     f"{ca['total']['median_s']} (IQR {ca['total']['iqr_s']})", f"{ratio:.2f}", winner,
                     f"{la.get('routine_median_s', '-')} / {ca.get('routine_median_s', '-')}",
                     f"{la.get('regional_median_s', '-')} / {ca.get('regional_median_s', '-')}"])
    table(["Part régionale", "Local (s)", "Citus-2 (s)", "Citus-2 / local", "Plus rapide", "F1 médiane local / Citus-2 (s)",
           "F2-F3 médiane local / Citus-2 (s)"], rows)
    print("Prédiction (docs/e3_prediction.md) : local meilleur à 0 %, Citus-2 meilleur à 100 %, basculement vers 1 à 5 %.")
    print(f"Mesuré : premier point où Citus-2 gagne = {crossover + ' %' if crossover else 'aucun'}.\n")


def e4() -> None:
    for c in ("citus2", "citus3"):
        d = load(f"e4_{c}")
        if not d:
            continue
        print(f"## E4 ({c}) : équilibre des données\n")
        table(["Worker", "Stations", "Observations", "Part", "Écart au partage égal"],
              [[n, w["stations"], f"{w['rows']:,}", f"{w['share_percent']} %", f"{w['vs_ideal_percent']} %"]
               for n, w in d["workers"].items()])
        s = d["shard_rows"]
        print(f"Shards avec données : {s['count']}, de {s['min']:,} à {s['max']:,} lignes (médiane {s['median']:,}, "
              f"max/médiane {s['max_over_median']}). Stations les plus lourdes : "
              + ", ".join(f"{h['station']} ({h['rows']:,})" for h in d["heaviest_stations"][:3]) + "\n")


def panne() -> None:
    d = load("panne")
    if not d:
        return
    print(f"## Perte d'une instance ({d['stopped_worker']} arrêté)\n")
    for step, cmds in d["steps"].items():
        print(f"**{step}**\n")
        table(["Commande", "Code", "Durée (s)", "Message"],
              [[k, v["exit_code"], v["seconds"], v["message"][:140]] for k, v in cmds.items()])
    for k, v in d["checks"].items():
        print(("- OK : " if v else "- ÉCHEC : ") + k)
    print()


if __name__ == "__main__":
    for f in (e1, e2, e3, e4, panne):
        f()
