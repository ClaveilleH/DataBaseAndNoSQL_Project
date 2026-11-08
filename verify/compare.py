"""Comparaison automatique : services (base, via DATABASE_URL) contre vérification indépendante (fichiers NOAA).

Usage : uv run python -m verify.compare
Les deux côtés sont comparés après tri canonique ; tout écart est affiché et le code de sortie vaut 1.
Les résultats sont écrits dans verify/results/ (paramètres, comptes, écarts).
"""

import json
import sys
from datetime import date
from pathlib import Path

from verify import f2_episodes as v2
from verify import f3_anomalies as v3
from verify.noaa import stations
from weatherscope.db import connect
from weatherscope.services import f2_episodes, f3_anomalies
from weatherscope.services.common import Area

OUT = Path(__file__).resolve().parent / "results"

F2_CASES = [  # zone, élément, début, fin, seuil (dixièmes), durée minimale
    ("SP", "TMAX", "2015-01-01", "2024-12-31", 400, 3),
    ("GM", "PRCP", "2015-01-01", "2024-12-31", 100, 2),
]
F3_CASES = [  # zone, élément, première et dernière année
    ("GM", "TMAX", 2015, 2024),
    ("SP", "PRCP", 2015, 2024),
]


def f2_key(e: dict) -> tuple:
    return (e["station"], e["start"], e["end"], e["days"], e["mean_excess"], e["max_value"])


def f3_key(m: dict) -> tuple:
    return (m["zone"], m["year"], m["month"], m["anomaly"], m["cells"], m["stations"])


def diff(name: str, service: list[tuple], independent: list[tuple]) -> dict:
    s, i = sorted(service), sorted(independent)
    only_s, only_i = sorted(set(s) - set(i)), sorted(set(i) - set(s))
    ok = s == i
    print(f"{'OK  ' if ok else 'ÉCART'} {name} : {len(s)} lignes (services), {len(i)} lignes (fichiers NOAA)")
    for row in only_s[:5]:
        print("   seulement services :", row)
    for row in only_i[:5]:
        print("   seulement fichiers :", row)
    return {"case": name, "identical": ok, "service_rows": len(s), "independent_rows": len(i),
            "only_service": only_s[:20], "only_independent": only_i[:20]}


def main() -> None:
    report = []
    with connect() as conn:
        for zone, el, start, end, thr, n in F2_CASES:
            s0, s1 = date.fromisoformat(start), date.fromisoformat(end)
            svc = f2_episodes.episodes(conn, Area(zones=[zone]), el, s0, s1, thr, n)["episodes"]
            ind = [e for sid in sorted(stations(zone)) for e in v2.episodes(sid, el, s0, s1, thr, n)]
            report.append(diff(f"F2 {zone} {el} >= {thr / 10} pendant {n} j, {start}..{end}",
                               [f2_key(e) for e in svc], [f2_key(e) for e in ind]))
        for zone, el, y0, y1 in F3_CASES:
            svc = f3_anomalies.anomalies(conn, [zone], el, y0, y1)["months"]
            ind = v3.ranked_months(zone, y0, y1, el)
            report.append(diff(f"F3 {zone} {el} {y0}..{y1}", [f3_key(m) for m in svc], [f3_key(m) for m in ind]))
            # Le classement lui-même doit aussi coïncider (même ordre, égalités départagées pareil).
            same_order = [f3_key(m) for m in svc] == [f3_key(m) for m in ind]
            print(f"     classement {'identique' if same_order else 'DIFFÉRENT'}")
            report[-1]["same_ranking"] = same_order

    OUT.mkdir(exist_ok=True)
    (OUT / "compare.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    sys.exit(0 if all(r["identical"] and r.get("same_ranking", True) for r in report) else 1)


if __name__ == "__main__":
    main()
