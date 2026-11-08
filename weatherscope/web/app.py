"""Interface web de WeatherScope (lecture seule) : F1 à F4 et traçabilité (D28).

Usage : uv run python -m weatherscope.web [--port 8050]
Mêmes services que la ligne de commande, même base (DATABASE_URL : local ou coordinateur Citus).
Chaque requête ouvre sa connexion ; si la base ou un worker manque, la réponse est une erreur 503
« ÉCHEC » et aucun résultat partiel n'est renvoyé, comme dans la CLI. F5 (import) n'est pas exposé :
il modifie la base et reste en ligne de commande.
"""

from datetime import date
from pathlib import Path
from typing import Annotated

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from weatherscope.db import connect
from weatherscope.services import (
    f1_station,
    f2_episodes,
    f3_anomalies,
    f4_regional,
    trace,
)
from weatherscope.services.common import Area, fetch, tenths

STATIC = Path(__file__).resolve().parent / "static"
ELEMENTS = ("TMAX", "TMIN", "PRCP")

app = FastAPI(title="WeatherScope", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

Zones = Annotated[list[str] | None, Query(description="GM (Allemagne), SP (Espagne) ; plusieurs possibles")]
Bbox = Annotated[str | None, Query(description="rectangle lat_min,lat_max,lon_min,lon_max")]
Element = Annotated[str, Query(pattern="^(TMAX|TMIN|PRCP)$")]


def area(zone: list[str] | None, bbox: str | None) -> Area:
    box = None
    if bbox:
        try:
            box = tuple(float(x) for x in bbox.split(","))
        except ValueError:
            box = ()
        if len(box) != 4:
            raise HTTPException(422, "rectangle attendu : lat_min,lat_max,lon_min,lon_max")
    if not zone and not box:
        raise HTTPException(422, "préciser une zone (GM, SP) ou un rectangle")
    return Area(zones=zone or None, bbox=box)


def run(compute):
    """Exécute un service ; en cas d'échec de la base, erreur 503 sans résultat partiel."""
    try:
        with connect() as conn:
            return compute(conn)
    except psycopg.Error as exc:
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        down = isinstance(exc, psycopg.OperationalError) or "remote node" in detail or "connection" in detail
        cause = "la base ou une de ses instances est indisponible" if down else "erreur de la base"
        raise HTTPException(503 if down else 500, f"ÉCHEC : {cause} ; la requête n'a pas été exécutée en entier. "
                                                  f"Détail : {detail}. Aucun résultat partiel n'est affiché.") from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info() -> dict:
    """Base interrogée : PostgreSQL seul ou Citus (et ses workers), volume chargé."""
    def compute(conn):
        out = {"postgres": fetch(conn, "SELECT split_part(version(), ' on ', 1) AS v", {})[0]["v"], "citus": None,
               "workers": []}
        try:
            with conn.transaction():
                out["citus"] = fetch(conn, "SELECT citus_version() AS v", {})[0]["v"].split(" on ")[0]
                out["workers"] = [r["nodename"] for r in fetch(
                    conn, "SELECT nodename FROM pg_dist_node WHERE noderole = 'primary' AND groupid > 0 "
                          "ORDER BY nodename", {})]
        except psycopg.errors.UndefinedFunction:
            pass
        out["stations"] = fetch(conn, "SELECT count(*) AS n FROM stations", {})[0]["n"]
        return out
    return run(compute)


@app.get("/api/stations")
def stations(zone: Zones = None, bbox: Bbox = None, name: str | None = None) -> dict:
    """F1 : stations d'une zone (toutes les stations si aucune zone n'est donnée, pour la carte)."""
    a = area(zone, bbox) if (zone or bbox) else Area(zones=["GM", "SP"])
    return run(lambda c: f1_station.search(c, a, name or None))


@app.get("/api/station/{station_id}")
def station(station_id: str, start: date, end: date) -> dict:
    """F1 : résumé mensuel d'une station sur un intervalle."""
    if end < start:
        raise HTTPException(422, "la fin précède le début")
    return run(lambda c: f1_station.summary(c, station_id, start, end))


@app.get("/api/episodes")
def episodes(start: date, end: date, threshold: float, element: Element = "TMAX", min_days: int = 3,
             zone: Zones = None, bbox: Bbox = None) -> dict:
    """F2 : épisodes de jours consécutifs au-dessus d'un seuil (en °C ou mm)."""
    a = area(zone, bbox)
    return run(lambda c: f2_episodes.episodes(c, a, element, start, end, tenths(threshold), min_days))


@app.get("/api/anomalies")
def anomalies(zone: Annotated[list[str], Query()], element: Element = "TMAX",
              first_year: int = 2015, last_year: int = 2024) -> dict:
    """F3 : mois anormaux par rapport à la normale 1991-2020."""
    return run(lambda c: f3_anomalies.anomalies(c, zone, element, first_year, last_year))


@app.get("/api/events")
def events(start: date, end: date, element: Element = "TMAX", quantile: float = 0.95, min_cells: int = 3,
           min_share: float = 0.25, zone: Zones = None, bbox: Bbox = None) -> dict:
    """F4 : événements régionaux et extrêmes isolés, avec leurs preuves."""
    a = area(zone, bbox)
    return run(lambda c: f4_regional.events(c, a, element, start, end, quantile, min_cells, min_share))


@app.get("/api/trace")
def trace_records(start: date | None = None, end: date | None = None, station: str | None = None,
                  zone: str | None = None, element: str | None = None, year: int | None = None,
                  month: int | None = None, flagged_only: bool = False, limit: int = 5000) -> dict:
    """Observations sources d'un résultat (champ « sources » de F1-F4)."""
    result = run(lambda c: trace.records(c, station=station, zone=zone, element=element or None, start=start,
                                         end=end, year=year, month=month, flagged_only=flagged_only))
    result["truncated"] = len(result["records"]) > limit
    result["records"] = result["records"][:limit]
    return result
