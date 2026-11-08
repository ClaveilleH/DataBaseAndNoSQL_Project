"""Import d'un lot NOAA dans la base : chargement initial et F5, même code (D10, D15, D16, D21).

Usage : uv run python -m ingest.load [fichiers ...] [--years 1991 2024] [--chunk 50]
- Sans fichier : tous les fichiers de data/raw/by_station/, années 1991-2024 (chargement initial).
- Avec des fichiers : n'importe quel extrait NOAA réel au format CSV GHCN-Daily
  (by_station ou by_year, .csv ou .csv.gz), toutes années sauf --years.
La base visée est DATABASE_URL (PostgreSQL local ou coordinateur Citus).

Lignes retenues : TMAX, TMIN, PRCP des stations allemandes (GM) ou espagnoles (SP).
Une station GM/SP absente de la base est ajoutée d'après data/raw/ghcnd-stations.txt ;
les lignes des autres pays sont ignorées et comptées.

Pour chaque paquet de fichiers, dans une seule transaction :
  1. COPY des lignes retenues dans observations_staging ;
  2. les observations existantes dont la valeur ou un flag change sont copiées dans observations_history ;
  3. INSERT ... ON CONFLICT DO UPDATE n'écrit que les lignes nouvelles ou modifiées ;
  4. monthly_stats est recalculée pour les mois touchés.
Réimporter les mêmes fichiers ne modifie aucune observation : seule une ligne de lot,
avec 0 nouvelle et 0 modifiée, est ajoutée à batches. Un import interrompu peut être relancé.
"""

import argparse
import csv
import gzip
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ingest.download import MANIFEST as DOWNLOAD_MANIFEST
from ingest.download import OUT_DIR, sha256
from ingest.select_stations import ZONES, read_stations
from weatherscope.db import connect

ROOT = Path(__file__).resolve().parent.parent
STATIONS_CSV = ROOT / "data" / "stations_selected.csv"
ELEMENTS = {"TMAX", "TMIN", "PRCP"}
INITIAL_YEARS = (1991, 2024)  # référence 1991-2020 + étude 2015-2024 (D16)

COLUMNS = "station, element, date, value, mflag, qflag, sflag, obs_time"

# Deux lignes du lot pour la même observation mais avec des valeurs différentes : on refuse le lot.
SQL_CONFLICTS = """
SELECT station, element, date FROM observations_staging
GROUP BY 1, 2, 3 HAVING count(DISTINCT (value, mflag, qflag, sflag, obs_time)) > 1 LIMIT 5
"""

SQL_HISTORY = f"""
INSERT INTO observations_history ({COLUMNS}, batch_id, replaced_by)
SELECT DISTINCT o.station, o.element, o.date, o.value, o.mflag, o.qflag, o.sflag, o.obs_time, o.batch_id, %(b)s
FROM observations o JOIN observations_staging s USING (station, element, date)
WHERE (o.value, o.mflag, o.qflag, o.sflag, o.obs_time)
      IS DISTINCT FROM (s.value, s.mflag, s.qflag, s.sflag, s.obs_time)
"""

# DISTINCT : un doublon exact dans le lot (même ligne dans deux fichiers) n'est écrit qu'une fois.
SQL_UPSERT = f"""
INSERT INTO observations ({COLUMNS}, batch_id)
SELECT DISTINCT {COLUMNS}, %(b)s::integer FROM observations_staging
ON CONFLICT (station, element, date) DO UPDATE
SET value = excluded.value, mflag = excluded.mflag, qflag = excluded.qflag,
    sflag = excluded.sflag, obs_time = excluded.obs_time, batch_id = excluded.batch_id
WHERE (observations.value, observations.mflag, observations.qflag, observations.sflag, observations.obs_time)
      IS DISTINCT FROM (excluded.value, excluded.mflag, excluded.qflag, excluded.sflag, excluded.obs_time)
"""

# Mois touchés = mois d'une ligne du paquet que ce lot vient d'écrire (nouvelle ou modifiée).
# Valide = qflag vide et mflag différent de P ; T (trace) est valide et compté à part (D20).
SQL_MONTHLY = """
INSERT INTO monthly_stats (station, element, year, month, n_obs, n_valid, n_flagged,
                           n_presumed, n_trace, sum_value, min_value, max_value)
SELECT o.station, o.element, extract(year FROM o.date)::smallint, extract(month FROM o.date)::smallint,
       count(*),
       count(*) FILTER (WHERE o.qflag IS NULL AND o.mflag IS DISTINCT FROM 'P'),
       count(*) FILTER (WHERE o.qflag IS NOT NULL),
       count(*) FILTER (WHERE o.qflag IS NULL AND o.mflag = 'P'),
       count(*) FILTER (WHERE o.qflag IS NULL AND o.mflag = 'T'),
       sum(o.value) FILTER (WHERE o.qflag IS NULL AND o.mflag IS DISTINCT FROM 'P'),
       min(o.value) FILTER (WHERE o.qflag IS NULL AND o.mflag IS DISTINCT FROM 'P'),
       max(o.value) FILTER (WHERE o.qflag IS NULL AND o.mflag IS DISTINCT FROM 'P')
FROM observations o
JOIN (SELECT DISTINCT s.station, s.element, date_trunc('month', s.date)::date AS month
      FROM observations_staging s
      JOIN observations w ON w.station = s.station AND w.element = s.element AND w.date = s.date
      WHERE w.batch_id = %(b)s) t
  ON o.station = t.station AND o.element = t.element
 AND o.date >= t.month AND o.date < t.month + interval '1 month'
GROUP BY 1, 2, 3, 4
ON CONFLICT (station, element, year, month) DO UPDATE
SET n_obs = excluded.n_obs, n_valid = excluded.n_valid, n_flagged = excluded.n_flagged,
    n_presumed = excluded.n_presumed, n_trace = excluded.n_trace, sum_value = excluded.sum_value,
    min_value = excluded.min_value, max_value = excluded.max_value
"""

STATION_COLS = "id, zone, name, lat, lon, elevation, wmo_id"
SQL_STATION = (f"INSERT INTO stations ({STATION_COLS}) VALUES (%s, %s, %s, %s, %s, %s, %s) "
               "ON CONFLICT (id) DO UPDATE SET zone = excluded.zone, name = excluded.name, lat = excluded.lat, "
               "lon = excluded.lon, elevation = excluded.elevation, wmo_id = excluded.wmo_id")


def load_stations(conn) -> None:
    """Met à jour la table stations à partir de data/stations_selected.csv."""
    with STATIONS_CSV.open(encoding="utf-8") as f:
        rows = [(r["id"], r["zone"], r["name"], r["lat"], r["lon"],
                 r["elevation"] or None, r["wmo_id"] or None) for r in csv.DictReader(f)]
    with conn.cursor() as cur:
        cur.executemany(SQL_STATION, rows)
    conn.commit()


def file_entries(paths: list[Path]) -> list[dict]:
    """Provenance des fichiers : reprise du manifeste de téléchargement si le SHA-256 correspond."""
    known = {}
    if DOWNLOAD_MANIFEST.exists():
        known = {e["path"]: e for e in json.loads(DOWNLOAD_MANIFEST.read_text())["files"]}
    entries = []
    for p in paths:
        rel = str(p.resolve().relative_to(ROOT)) if p.resolve().is_relative_to(ROOT) else str(p.resolve())
        digest = sha256(p)
        e = known.get(rel)
        if e and e["sha256"] == digest:
            entries.append({k: e[k] for k in ("url", "path", "retrieved_at", "size", "sha256")})
        else:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            entries.append({"url": None, "path": rel, "retrieved_at": mtime.isoformat(timespec="seconds"),
                            "size": p.stat().st_size, "sha256": digest})
    return entries


def copy_files(cur, paths: list[Path], years: tuple[int, int] | None, counts: dict) -> None:
    """COPY des lignes retenues vers observations_staging.

    Format CSV GHCN-Daily (by_station et by_year) : ID,AAAAMMJJ,ELEMENT,VALEUR,MFLAG,QFLAG,SFLAG,HEURE.
    """
    sql = ("COPY observations_staging (station, date, element, value, mflag, qflag, sflag, obs_time) "
           "FROM STDIN (FORMAT csv)")
    with cur.copy(sql) as copy:
        for p in paths:
            buf = []
            opener = gzip.open if p.suffix == ".gz" else open
            with opener(p, "rt", encoding="ascii") as f:
                for line in f:
                    if line[21:25] not in ELEMENTS or not line[12:16].isdigit():
                        continue  # autre élément, ou ligne d'en-tête
                    if years and not years[0] <= int(line[12:16]) <= years[1]:
                        continue
                    if line[:2] not in ZONES:
                        counts["ignored_other_zones"] += 1
                        continue
                    buf.append(line)
                    if len(buf) >= 100_000:
                        copy.write("".join(buf))
                        counts["read"] += len(buf)
                        buf = []
            copy.write("".join(buf))
            counts["read"] += len(buf)


def add_new_stations(cur, counts: dict) -> None:
    """Stations GM/SP du lot absentes de la base : ajoutées d'après ghcnd-stations.txt, sinon écartées."""
    cur.execute("SELECT DISTINCT station FROM observations_staging "
                "WHERE station NOT IN (SELECT id FROM stations) ORDER BY 1")
    missing = [r[0] for r in cur.fetchall()]
    if not missing:
        return
    meta = read_stations()
    known = [m for m in missing if m in meta]
    unknown = [m for m in missing if m not in meta]
    fields = ("id", "zone", "name", "lat", "lon", "elevation", "wmo_id")
    cur.executemany(SQL_STATION, [tuple(meta[m][k] for k in fields) for m in known])
    counts["new_stations"] += known
    if unknown:
        cur.execute("DELETE FROM observations_staging WHERE station = ANY(%s)", (unknown,))
        counts["ignored_unknown_station"] += cur.rowcount


def import_files(conn, paths: list[Path], years: tuple[int, int] | None = None, chunk: int = 50,
                 log: Callable[[str], None] = print) -> dict:
    """Importe les fichiers comme un lot ; renvoie les comptes du lot (aussi enregistrés dans batches)."""
    load_stations(conn)
    files = file_entries(paths)
    with conn.cursor() as cur:
        cur.execute("SELECT coalesce(max(id), 0) + 1, count(*) = 0 FROM batches")
        batch_id, first = cur.fetchone()
        cur.execute("INSERT INTO batches (id, kind, retrieved_at, files) VALUES (%s, %s, %s, %s)",
                    (batch_id, "initial" if first else "update",
                     min(e["retrieved_at"] for e in files), json.dumps(files)))
    conn.commit()

    counts = {"batch": batch_id, "read": 0, "inserted": 0, "updated": 0, "unchanged": 0,
              "ignored_other_zones": 0, "ignored_unknown_station": 0, "new_stations": []}
    try:
        for i in range(0, len(paths), chunk):
            part = paths[i:i + chunk]
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("TRUNCATE observations_staging")
                copy_files(cur, part, years, counts)
                add_new_stations(cur, counts)
                cur.execute(SQL_CONFLICTS)
                if bad := cur.fetchall():
                    raise ValueError(f"lot incohérent : mêmes observations avec des valeurs différentes, ex. {bad}")
                cur.execute(SQL_HISTORY, {"b": batch_id})
                updated = cur.rowcount
                cur.execute(SQL_UPSERT, {"b": batch_id})
                counts["inserted"] += cur.rowcount - updated  # rowcount = nouvelles + modifiées
                counts["updated"] += updated
                cur.execute(SQL_MONTHLY, {"b": batch_id})
                cur.execute("TRUNCATE observations_staging")
            # Lignes retenues moins écrites ; un doublon exact compte comme inchangé.
            counts["unchanged"] = (counts["read"] - counts["ignored_unknown_station"]
                                   - counts["inserted"] - counts["updated"])
            with conn.cursor() as cur:  # avancement visible dans batches, même si l'import s'arrête
                cur.execute("UPDATE batches SET counts = %s WHERE id = %s",
                            (json.dumps({**counts, "files_done": i + len(part)}), batch_id))
            conn.commit()
            log(f"lot {batch_id} : {i + len(part)}/{len(paths)} fichiers, {counts['read']:,} lues, "
                f"{counts['inserted']:,} nouvelles, {counts['updated']:,} modifiées")
    except Exception as exc:
        # Lot interrompu : l'erreur est notée dans batches ; relancer l'import est sans risque.
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("UPDATE batches SET counts = coalesce(counts, '{}') || %s WHERE id = %s",
                        (json.dumps({"error": str(exc).splitlines()[0]}), batch_id))
        conn.commit()
        raise
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path, help="fichiers NOAA (défaut : tout data/raw/by_station)")
    parser.add_argument("--years", type=int, nargs=2,
                        help="années retenues (défaut : 1991 2024 sans fichier, toutes avec des fichiers)")
    parser.add_argument("--chunk", type=int, default=50, help="fichiers par transaction")
    args = parser.parse_args()
    paths = sorted(args.files) if args.files else sorted(OUT_DIR.glob("*.csv.gz"))
    years = tuple(args.years) if args.years else (None if args.files else INITIAL_YEARS)
    with connect() as conn:
        print(json.dumps(import_files(conn, paths, years, args.chunk)))


if __name__ == "__main__":
    main()
