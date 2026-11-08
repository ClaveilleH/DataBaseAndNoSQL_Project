"""Description du jeu de données et anomalies, calculées directement depuis les fichiers NOAA (sans la base).

Usage : uv run python -m verify.data_report
Écrit docs/data_report.md (tableaux pour le rapport) et verify/results/data_report.json.
Périmètre : stations retenues, TMAX/TMIN/PRCP, 1991-2024 (étude 2015-2024, référence 1991-2014 comptée à part).
"""

import gzip
import itertools
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from verify.noaa import BY_STATION, ROOT, stations

ELEMENTS = ("TMAX", "TMIN", "PRCP")
STUDY = (2015, 2024)
FIRST = 1991
OUT_MD = ROOT / "docs" / "data_report.md"
OUT_JSON = Path(__file__).resolve().parent / "results" / "data_report.json"
EXAMPLES = 3


def period(year: int) -> str:
    return "study" if year >= STUDY[0] else "reference"


def main() -> None:
    meta = stations()
    obs = Counter()            # (zone, période, élément, état) -> nombre
    station_days = Counter()   # (zone, période) -> couples station-jour
    per_year = Counter()       # (zone, année) -> observations
    active = defaultdict(set)  # (zone, période, élément) -> stations
    anomalies: dict[str, dict] = defaultdict(lambda: {"count": 0, "examples": []})
    qflags = Counter()

    def note(kind: str, example: str) -> None:
        a = anomalies[kind]
        a["count"] += 1
        if len(a["examples"]) < EXAMPLES:
            a["examples"].append(example)

    for sid in sorted(meta):
        zone = meta[sid]["zone"]
        days: dict[date, dict] = defaultdict(dict)
        with gzip.open(BY_STATION / f"{sid}.csv.gz", "rt", encoding="ascii") as f:
            for line in f:
                _s, day, el, value, mflag, qflag, _sf, _t = line.rstrip("\n").split(",")
                y = int(day[:4])
                if el not in ELEMENTS or not FIRST <= y <= STUDY[1]:
                    continue
                d = date(y, int(day[4:6]), int(day[6:]))
                v = int(value)
                days[d][el] = (v, mflag, qflag)
                p = period(y)
                state = "flagged" if qflag else ("presumed" if mflag == "P" else "valid")
                obs[(zone, p, el, state)] += 1
                per_year[(zone, y)] += 1
                active[(zone, p, el)].add(sid)
                if qflag:
                    qflags[qflag] += 1
                    note(f"qflag {qflag}", f"{sid} {d} {el}={v}")
                if mflag == "T":
                    note("PRCP trace (T)", f"{sid} {d} PRCP={v} T")
                if not qflag and ((el in ("TMAX", "TMIN") and not -400 <= v <= 480) or (el == "PRCP" and v > 2000)):
                    note("valeur extrême sans qflag (T < -40 °C, T > 48 °C, pluie > 200 mm)", f"{sid} {d} {el}={v}")

        for d, els in days.items():
            station_days[(zone, period(d.year))] += 1
            tx, tn = els.get("TMAX"), els.get("TMIN")
            if tx and tn and not tx[2] and not tn[2] and tx[0] < tn[0]:
                note("TMAX < TMIN le même jour (sans qflag)", f"{sid} {d} TMAX={tx[0]} TMIN={tn[0]}")

        # Trous : au moins 30 jours sans aucune observation pendant la période d'étude, entre deux observations.
        study_days = sorted(d for d in days if d.year >= STUDY[0])
        for a, b in itertools.pairwise(study_days):
            if (b - a).days > 30:
                note("trou de plus de 30 jours (2015-2024)", f"{sid} du {a + timedelta(days=1)} au {b - timedelta(days=1)}")
        if study_days:
            if study_days[0] > date(STUDY[0], 1, 31):
                note("station qui commence pendant 2015-2024", f"{sid} première observation {study_days[0]}")
            if study_days[-1] < date(STUDY[1], 12, 1):
                note("station qui s'arrête pendant 2015-2024", f"{sid} dernière observation {study_days[-1]}")

    report = {
        "stations": {z: sum(1 for m in meta.values() if m["zone"] == z) for z in ("GM", "SP")},
        "cells": {z: len({m["cell"] for m in meta.values() if m["zone"] == z}) for z in ("GM", "SP")},
        "station_days": {f"{z} {p}": n for (z, p), n in sorted(station_days.items())},
        "observations": {f"{z} {p} {e} {s}": n for (z, p, e, s), n in sorted(obs.items())},
        "active_stations": {f"{z} {p} {e}": len(v) for (z, p, e), v in sorted(active.items())},
        "per_year": {f"{z} {y}": n for (z, y), n in sorted(per_year.items())},
        "qflags": dict(qflags.most_common()),
        "anomalies": dict(sorted(anomalies.items(), key=lambda kv: -kv[1]["count"])),
    }
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, obs, station_days, active)
    print(f"écrit : {OUT_MD.relative_to(ROOT)}, {OUT_JSON.relative_to(ROOT)}")


def write_markdown(r: dict, obs: Counter, station_days: Counter, active: dict) -> None:
    lines = ["# Jeu de données : chiffres et anomalies",
             "",
             ("Calculé par `verify/data_report.py` directement depuis les fichiers NOAA `by_station` "
              "(sans la base). Périmètre : 774 stations, TMAX/TMIN/PRCP, 1991–2024."),
             "",
             "## Stations et couples station-jour",
             "",
             "| Zone | Stations | Mailles 0,5° | Station-jours 2015–2024 | Station-jours 1991–2014 (référence seule) |",
             "| --- | --- | --- | --- | --- |"]
    for z in ("GM", "SP"):
        lines.append(f"| {z} | {r['stations'][z]} | {r['cells'][z]} | {station_days[(z, 'study')]:,} | "
                     f"{station_days[(z, 'reference')]:,} |")
    lines += ["", "## Observations par élément", "",
              "Valides = sans qflag et sans mflag P. Les observations 2015–2020 servent aussi à la référence 1991–2020.",
              "",
              "| Zone | Élément | Période | Stations actives | Valides | Invalides (qflag) | P |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for z in ("GM", "SP"):
        for e in ELEMENTS:
            for p, label in (("study", "2015–2024"), ("reference", "1991–2014")):
                lines.append(f"| {z} | {e} | {label} | {len(active[(z, p, e)])} | {obs[(z, p, e, 'valid')]:,} | "
                             f"{obs[(z, p, e, 'flagged')]:,} | {obs[(z, p, e, 'presumed')]:,} |")
    total = sum(obs.values())
    lines += ["", f"Total : {total:,} observations brutes.", "",
              "## Observations par année", "", "| Année | GM | SP |", "| --- | --- | --- |"]
    years = sorted({int(k.split()[1]) for k in r["per_year"]})
    for y in years:
        lines.append(f"| {y} | {r['per_year'].get(f'GM {y}', 0):,} | {r['per_year'].get(f'SP {y}', 0):,} |")
    lines += ["", "## Anomalies présentes dans les données", "",
              ("Fréquence sur 1991–2024 (les trous et les débuts ou fins de station : sur 2015–2024), "
               "avec des exemples vérifiables dans les fichiers NOAA (valeurs en dixièmes)."), "",
              "| Anomalie | Fréquence | Exemples |", "| --- | --- | --- |"]
    for kind, a in r["anomalies"].items():
        lines.append(f"| {kind} | {a['count']:,} | {'<br>'.join(a['examples'])} |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
