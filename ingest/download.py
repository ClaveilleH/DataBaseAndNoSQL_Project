"""Téléchargement des fichiers de mesures NOAA (by_station) des stations retenues.

Usage : uv run python ingest/download.py [--workers 8]
Lit data/stations_selected.csv, télécharge by_station/<id>.csv.gz dans data/raw/by_station/
(un fichier déjà présent n'est pas retéléchargé), puis écrit le manifeste du lot
dans data/manifest/by_station.json : URL, date de récupération, taille et SHA-256 de chaque fichier.
"""

import argparse
import csv
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

BASE_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/"
ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "data" / "stations_selected.csv"
OUT_DIR = ROOT / "data" / "raw" / "by_station"
MANIFEST = ROOT / "data" / "manifest" / "by_station.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(station_id: str) -> dict:
    url = f"{BASE_URL}{station_id}.csv.gz"
    path = OUT_DIR / f"{station_id}.csv.gz"
    if not path.exists():
        tmp = path.with_suffix(".part")  # fichier complet seulement une fois renommé
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(path)
    retrieved = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return {
        "station": station_id,
        "url": url,
        "path": str(path.relative_to(ROOT)),
        "retrieved_at": retrieved.isoformat(timespec="seconds"),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8, help="téléchargements en parallèle")
    args = parser.parse_args()

    with STATIONS.open(encoding="utf-8") as f:
        ids = [row["id"] for row in csv.DictReader(f)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    entries, errors = [], []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {sid: pool.submit(fetch, sid) for sid in ids}
        for sid, fut in futures.items():
            try:
                entries.append(fut.result())
            except Exception as exc:  # noqa: BLE001 — noté dans le manifeste, jamais ignoré en silence
                errors.append({"station": sid, "error": str(exc)})

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "source": BASE_URL,
        "stations": len(ids),
        "downloaded": len(entries),
        "total_bytes": sum(e["size"] for e in entries),
        "errors": errors,
        "files": entries,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(entries)}/{len(ids)} fichiers, {sum(e['size'] for e in entries) / 1e6:.0f} Mo, "
          f"{len(errors)} erreurs -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
