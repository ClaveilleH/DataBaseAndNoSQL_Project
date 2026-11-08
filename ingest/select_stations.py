"""Sélection des stations du périmètre (Allemagne + Espagne) à partir des métadonnées NOAA.

Usage : python ingest/select_stations.py
Télécharge au besoin ghcnd-stations.txt, ghcnd-inventory.txt et ghcnd-countries.txt dans data/raw/,
écrit leur manifeste (URL, date de récupération, SHA-256) dans data/manifest/metadata.json,
puis la liste des stations retenues dans data/stations_selected.csv.
Bibliothèque standard uniquement.
"""

import csv
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
FILES = ["ghcnd-stations.txt", "ghcnd-inventory.txt", "ghcnd-countries.txt"]
ZONES = {"GM": "Allemagne", "SP": "Espagne"}
ELEMENTS = ["TMAX", "TMIN", "PRCP"]
STUDY = (2015, 2024)
BASELINE = (1991, 2020)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest" / "metadata.json"
OUTPUT = ROOT / "data" / "stations_selected.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_metadata() -> list[dict]:
    """Télécharge les fichiers manquants et renvoie leur manifeste."""
    RAW.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in FILES:
        path = RAW / name
        if not path.exists():
            urllib.request.urlretrieve(BASE_URL + name, path)
        # Date de récupération = date d'écriture du fichier local.
        retrieved = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        entries.append({
            "url": BASE_URL + name,
            "path": str(path.relative_to(ROOT)),
            "retrieved_at": retrieved.isoformat(timespec="seconds"),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    return entries


def read_stations() -> dict[str, dict]:
    """Format fixe décrit dans readme.txt (section IV)."""
    stations = {}
    with (RAW / "ghcnd-stations.txt").open(encoding="utf-8") as f:
        for line in f:
            sid = line[0:11]
            if sid[:2] not in ZONES:
                continue
            elev = float(line[31:37])
            stations[sid] = {
                "id": sid,
                "zone": sid[:2],
                "name": line[41:71].strip(),
                "lat": float(line[12:20]),
                "lon": float(line[21:30]),
                "elevation": None if elev == -999.9 else elev,  # -999.9 = inconnue
                "wmo_id": line[80:85].strip() or None,
            }
    return stations


def read_inventory() -> dict[str, dict[str, tuple[int, int]]]:
    """Première et dernière année par station et par élément (section VII de readme.txt)."""
    inventory: dict[str, dict[str, tuple[int, int]]] = {}
    with (RAW / "ghcnd-inventory.txt").open(encoding="utf-8") as f:
        for line in f:
            sid, element = line[0:11], line[31:35]
            if sid[:2] in ZONES and element in ELEMENTS:
                inventory.setdefault(sid, {})[element] = (int(line[36:40]), int(line[41:45]))
    return inventory


def covers(span: tuple[int, int] | None, period: tuple[int, int]) -> bool:
    return span is not None and span[0] <= period[0] and span[1] >= period[1]


def overlaps(span: tuple[int, int] | None, period: tuple[int, int]) -> bool:
    return span is not None and span[0] <= period[1] and span[1] >= period[0]


def main() -> None:
    manifest = fetch_metadata()
    stations = read_stations()
    inventory = read_inventory()

    # Retenue = au moins un élément (TMAX, TMIN, PRCP) actif pendant la période d'étude.
    # Les stations qui commencent ou s'arrêtent en cours de période sont gardées
    # (anomalies à documenter) ; la colonne full_study permet de les filtrer.
    rows = []
    for sid, inv in sorted(inventory.items()):
        if sid not in stations or not any(overlaps(inv.get(e), STUDY) for e in ELEMENTS):
            continue
        row = dict(stations[sid])
        for e in ELEMENTS:
            span = inv.get(e)
            row[f"{e.lower()}_first"] = span[0] if span else None
            row[f"{e.lower()}_last"] = span[1] if span else None
        row["full_study"] = any(covers(inv.get(e), STUDY) for e in ELEMENTS)
        row["baseline_tmax"] = covers(inv.get("TMAX"), BASELINE)
        rows.append(row)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        z: {
            "selected": sum(r["zone"] == z for r in rows),
            "full_study": sum(r["zone"] == z and r["full_study"] for r in rows),
            "baseline_tmax": sum(r["zone"] == z and r["baseline_tmax"] for r in rows),
        }
        for z in ZONES
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "zones": ZONES, "study": STUDY, "baseline": BASELINE,
        "files": manifest, "stations": summary,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
