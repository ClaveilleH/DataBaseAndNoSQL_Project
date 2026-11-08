"""Import d'un lot NOAA by_station dans la base (chargement initial et F5, même code).

Usage : uv run python -m ingest.load [fichiers.csv.gz ...] [--chunk 50]
Sans fichier : tous les fichiers de data/raw/by_station/. La base visée est DATABASE_URL
(PostgreSQL local ou coordinateur Citus) ; le schéma sql/schema.sql doit être chargé.

Pour chaque paquet de stations, dans une seule transaction (décisions D10, D15) :
  1. COPY des lignes retenues (TMAX/TMIN/PRCP, 1991-2024) dans observations_staging ;
  2. les observations existantes dont la valeur ou un flag change sont copiées dans observations_history ;
  3. INSERT ... ON CONFLICT DO UPDATE n'écrit que les lignes nouvelles ou modifiées ;
  4. monthly_stats est recalculée pour les mois touchés par ce lot.
Réimporter les mêmes fichiers ne modifie donc aucune observation : seule une ligne de lot,
avec 0 insertion et 0 modification, est ajoutée à batches. Un import interrompu peut être relancé.
"""

import argparse
import csv
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from ingest.download import MANIFEST as DOWNLOAD_MANIFEST
from ingest.download import OUT_DIR, sha256
from weatherscope.db import connect

ROOT = Path(__file__).resolve().parent.parent
STATIONS_CSV = ROOT / "data" / "stations_selected.csv"
ELEMENTS = {"TMAX", "TMIN", "PRCP"}
YEARS = (1991, 2024)  # référence 1991-2020 + étude 2015-2024 (D16)

COLUMNS = "station, element, date, value, mflag, qflag, sflag, obs_time"
CHANGED = ("(o.value, o.mflag, o.qflag, o.sflag, o.obs_time) "
           "IS DISTINCT FROM (s.value, s.mflag, s.qflag, s.sflag, s.obs_time)")

SQL_HISTORY = f"""
INSERT INTO observations_history ({COLUMNS}, batch_id, replaced_by)
SELECT o.station, o.element, o.date, o.value, o.mflag, o.qflag, o.sflag, o.obs_time, o.batch_id, %(b)s
FROM observations o JOIN observations_staging s USING (station, element, date)
WHERE {CHANGED}
"""

SQL_UPSERT = f"""
INSERT INTO observations ({COLUMNS}, batch_id)
SELECT {COLUMNS}, %(b)s FROM observations_staging
ON CONFLICT (station, element, date) DO UPDATE
SET value = excluded.value, mflag = excluded.mflag, qflag = excluded.qflag,
    sflag = excluded.sflag, obs_time = excluded.obs_time, batch_id = excluded.batch_id
WHERE (observations.value, observations.mflag, observations.qflag, observations.sflag, observations.obs_time)
      IS DISTINCT FROM (excluded.value, excluded.mflag, excluded.qflag, excluded.sflag, excluded.obs_time)
"""

# Mois touchés = mois contenant une observation écrite par ce lot, pour les stations du paquet.
# Sommes et comptes entiers ; P/T (PRCP) comptées à part dans n_pt (D9).
SQL_MONTHLY = """
INSERT INTO monthly_stats
SELECT o.station, o.element, extract(year FROM o.date)::smallint, extract(month FROM o.date)::smallint,
       count(*),
       count(*) FILTER (WHERE o.qflag IS NULL),
       count(*) FILTER (WHERE o.qflag IS NOT NULL),
       count(*) FILTER (WHERE o.qflag IS NULL AND o.element = 'PRCP' AND o.mflag IN ('P', 'T')),
       sum(o.value) FILTER (WHERE o.qflag IS NULL),
       min(o.value) FILTER (WHERE o.qflag IS NULL),
       max(o.value) FILTER (WHERE o.qflag IS NULL)
FROM observations o
JOIN (SELECT DISTINCT station, element, date_trunc('month', date)::date AS month
      FROM observations WHERE batch_id = %(b)s AND station = ANY(%(stations)s)) t
  ON o.station = t.station AND o.element = t.element
 AND o.date >= t.month AND o.date < t.month + interval '1 month'
GROUP BY 1, 2, 3, 4
ON CONFLICT (station, element, year, month) DO UPDATE
SET n_obs = excluded.n_obs, n_valid = excluded.n_valid, n_flagged = excluded.n_flagged,
    n_pt = excluded.n_pt, sum_value = excluded.sum_value,
    min_value = excluded.min_value, max_value = excluded.max_value
"""


def load_stations(conn) -> None:
    """Met à jour la table stations à partir de data/stations_selected.csv."""
    with STATIONS_CSV.open(encoding="utf-8") as f:
        rows = [(r["id"], r["zone"], r["name"], r["lat"], r["lon"],
                 r["elevation"] or None, r["wmo_id"] or None) for r in csv.DictReader(f)]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO stations (id, zone, name, lat, lon, elevation, wmo_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
            "zone = excluded.zone, name = excluded.name, lat = excluded.lat, lon = excluded.lon, "
            "elevation = excluded.elevation, wmo_id = excluded.wmo_id", rows)
    conn.commit()


def file_entries(paths: list[Path]) -> list[dict]:
    """Provenance des fichiers : reprise du manifeste de téléchargement si le SHA-256 correspond."""
    known = {}
    if DOWNLOAD_MANIFEST.exists():
        known = {e["path"]: e for e in json.loads(DOWNLOAD_MANIFEST.read_text())["files"]}
    entries = []
    for p in paths:
        rel = str(p.resolve().relative_to(ROOT)) if p.resolve().is_relative_to(ROOT) else str(p)
        digest = sha256(p)
        e = known.get(rel)
        if e and e["sha256"] == digest:
            entries.append({k: e[k] for k in ("url", "path", "retrieved_at", "size", "sha256")})
        else:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            entries.append({"url": None, "path": rel, "retrieved_at": mtime.isoformat(timespec="seconds"),
                            "size": p.stat().st_size, "sha256": digest})
    return entries


def copy_files(cur, paths: list[Path]) -> int:
    """COPY des lignes retenues vers observations_staging. Renvoie le nombre de lignes lues."""
    n = 0
    # Colonnes dans l'ordre du fichier NOAA (la date avant l'élément).
    sql = ("COPY observations_staging (station, date, element, value, mflag, qflag, sflag, obs_time) "
           "FROM STDIN (FORMAT csv)")
    with cur.copy(sql) as copy:
        for p in paths:
            buf = []
            with gzip.open(p, "rt", encoding="ascii") as f:
                # Format by_station : ID,AAAAMMJJ,ELEMENT,VALEUR,MFLAG,QFLAG,SFLAG,HEURE (champ vide = NULL).
                for line in f:
                    if line[21:25] in ELEMENTS and YEARS[0] <= int(line[12:16]) <= YEARS[1]:
                        buf.append(line)
            copy.write("".join(buf))
            n += len(buf)
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path, help="fichiers by_station (défaut : tous)")
    parser.add_argument("--chunk", type=int, default=50, help="stations par transaction")
    args = parser.parse_args()
    paths = sorted(args.files or OUT_DIR.glob("*.csv.gz"))

    with connect() as conn:
        load_stations(conn)
        files = file_entries(paths)
        with conn.cursor() as cur:
            cur.execute("SELECT coalesce(max(id), 0) + 1, count(*) = 0 FROM batches")
            batch_id, first = cur.fetchone()
            cur.execute(
                "INSERT INTO batches (id, kind, retrieved_at, files) VALUES (%s, %s, %s, %s)",
                (batch_id, "initial" if first else "update",
                 min(e["retrieved_at"] for e in files), json.dumps(files)))
        conn.commit()

        totals = {"read": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        try:
            import_chunks(conn, paths, batch_id, args.chunk, totals)
        except Exception as exc:
            # Lot interrompu : l'erreur est notée dans batches ; relancer l'import est sans risque.
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("UPDATE batches SET counts = coalesce(counts, '{}') || %s WHERE id = %s",
                            (json.dumps({"error": str(exc).splitlines()[0]}), batch_id))
            conn.commit()
            raise

    print(json.dumps({"batch": batch_id, **totals}))


def import_chunks(conn, paths: list[Path], batch_id: int, chunk: int, totals: dict) -> None:
    for i in range(0, len(paths), chunk):
        part = paths[i:i + chunk]
        stations = [p.name.split(".")[0] for p in part]
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("TRUNCATE observations_staging")
            read = copy_files(cur, part)
            cur.execute(SQL_HISTORY, {"b": batch_id})
            updated = cur.rowcount
            cur.execute(SQL_UPSERT, {"b": batch_id})
            written = cur.rowcount  # nouvelles + modifiées
            cur.execute(SQL_MONTHLY, {"b": batch_id, "stations": stations})
            cur.execute("TRUNCATE observations_staging")
        totals["read"] += read
        totals["inserted"] += written - updated
        totals["updated"] += updated
        totals["unchanged"] = totals["read"] - totals["inserted"] - totals["updated"]
        with conn.cursor() as cur:  # avancement visible dans batches, même si l'import s'arrête
            cur.execute("UPDATE batches SET counts = %s WHERE id = %s",
                        (json.dumps({**totals, "stations_done": i + len(part)}), batch_id))
        conn.commit()
        print(f"lot {batch_id} : {i + len(part)}/{len(paths)} stations, "
              f"{totals['read']:,} lues, {totals['inserted']:,} nouvelles, {totals['updated']:,} modifiées",
              flush=True)


if __name__ == "__main__":
    main()
