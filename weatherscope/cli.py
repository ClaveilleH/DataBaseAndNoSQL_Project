"""Interface WeatherScope en ligne de commande (services F1-F5 et traçabilité).

Usage : uv run python -m weatherscope.cli --help
La base visée est DATABASE_URL : PostgreSQL local ou coordinateur Citus, avec les mêmes commandes.
Options communes : --json (résultat complet, ordre canonique, pour la comparaison automatique)
et --explain (plan d'exécution : en distribué, tâches et workers contactés).
Si la base ou une instance ne répond pas, la commande échoue explicitement (code 2) :
aucun résultat partiel n'est affiché.
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import psycopg
import typer
from rich.console import Console
from rich.table import Table

from weatherscope.db import connect
from weatherscope.services import (
    f1_station,
    f2_episodes,
    f3_anomalies,
    f4_regional,
    trace,
)
from weatherscope.services.common import Area, explain, tenths

app = typer.Typer(add_completion=False, no_args_is_help=True, help="WeatherScope : observatoire météo NOAA GHCN-Daily")
console = Console()

Zone = Annotated[list[str] | None, typer.Option("--zone", "-z", help="pays : GM (Allemagne), SP (Espagne)")]
Bbox = Annotated[tuple[float, float, float, float] | None,
                 typer.Option(help="rectangle : lat_min lat_max lon_min lon_max")]
Json = Annotated[bool, typer.Option("--json", help="sortie JSON complète")]
Explain = Annotated[bool, typer.Option("--explain", help="afficher le plan d'exécution")]
Day = Annotated[str, typer.Option(help="date AAAA-MM-JJ")]


def area(zone, bbox) -> Area:
    if not zone and not bbox:
        raise typer.BadParameter("préciser --zone ou --bbox")
    return Area(zones=zone or None, bbox=tuple(bbox) if bbox else None)


def run(compute, as_json: bool, show) -> None:
    """Exécute un service ; en cas d'échec de la base, message explicite et aucun résultat partiel."""
    try:
        with connect() as conn:
            result = compute(conn)
    except psycopg.Error as exc:
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        # Connexion perdue ou worker Citus injoignable (« connection to the remote node ... failed »).
        down = isinstance(exc, psycopg.OperationalError) or "remote node" in detail or "connection" in detail
        cause = "la base ou une de ses instances est indisponible" if down else "erreur de la base"
        console.print(f"[bold red]ÉCHEC[/] : {cause} ; la requête n'a pas été exécutée en entier.\n"
                      f"Détail : {detail}\nAucun résultat partiel n'est affiché.")
        raise typer.Exit(2) from exc
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    else:
        show(result)


def show_plan(sql: str, params: dict) -> None:
    with connect() as conn:
        for line in explain(conn, sql, params):
            console.print(line, highlight=False, markup=False)
    console.rule()


def table(title: str, rows: list[dict], cols: list[str], limit: int | None = None) -> None:
    t = Table(title=title)
    for c in cols:
        t.add_column(c)
    for r in rows[:limit] if limit else rows:
        t.add_row(*("" if r.get(c) is None else str(r.get(c)) for c in cols))
    console.print(t)
    if limit and len(rows) > limit:
        console.print(f"... {len(rows) - limit} lignes de plus (--json pour tout voir)")


@app.command()
def stations(zone: Zone = None, bbox: Bbox = None, name: str | None = None, as_json: Json = False) -> None:
    """F1 : chercher des stations dans une zone."""
    a = area(zone, bbox)
    run(lambda c: f1_station.search(c, a, name), as_json,
        lambda r: table(f"{len(r['stations'])} stations", r["stations"], ["id", "zone", "name", "lat", "lon",
                                                                          "elevation"]))


@app.command()
def station(station_id: str, start: Day, end: Day, as_json: Json = False, show_explain: Explain = False) -> None:
    """F1 : résumé mensuel d'une station (disponibilité, qualité, moyennes, cumuls)."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if show_explain:
        show_plan(f1_station.SQL_SUMMARY, {"station": station_id, "start": s, "end": e})

    def show(r):
        st = r["station"]
        console.print(f"[bold]{st['id']}[/] {st['name']} ({st['zone']}), lat {st['lat']}, lon {st['lon']}, "
                      f"altitude {st['elevation']} m")
        for el, t in r["totals"].items():
            console.print(f"  {el} : {t['n_valid']}/{t['expected']} jours valides (disponibilité {t['availability']}), "
                          f"{t['n_flagged']} invalides (qflag), {t['n_trace']} traces, {t['n_presumed']} présumées nulles")
        table("Résumé mensuel", r["months"], ["element", "year", "month", "expected", "n_valid", "n_flagged",
                                               "availability", "mean", "total", "min", "max", "unit"])
        console.print(f"Sources : trace --station {station_id} --start {start} --end {end}")
    run(lambda c: f1_station.summary(c, station_id, s, e), as_json, show)


@app.command()
def episodes(start: Day, end: Day, threshold: Annotated[float, typer.Option(help="seuil en °C ou mm")],
             zone: Zone = None, bbox: Bbox = None,
             element: Annotated[str, typer.Option(help="TMAX, TMIN ou PRCP")] = "TMAX",
             min_days: Annotated[int, typer.Option(help="durée minimale en jours")] = 3,
             limit: int = 20, as_json: Json = False, show_explain: Explain = False) -> None:
    """F2 : épisodes de jours consécutifs avec élément >= seuil."""
    a, s, e, thr = area(zone, bbox), date.fromisoformat(start), date.fromisoformat(end), tenths(threshold)
    if show_explain:
        show_plan(*f2_episodes.query(a, element, s, e, thr, min_days))

    def show(r):
        rows = sorted(r["episodes"], key=lambda x: (-x["days"], -x["mean_excess"], x["station"], x["start"]))
        table(f"{r['count']} épisodes {element} >= {r['params']['threshold']} {r['unit']} pendant {min_days} jours "
              "ou plus (les plus longs)", rows, ["station", "start", "end", "days", "mean_excess", "max_value"], limit)
        console.print("Sources d'un épisode : trace --station ID --element " + element + " --start DEBUT --end FIN")
    run(lambda c: f2_episodes.episodes(c, a, element, s, e, thr, min_days), as_json, show)


@app.command()
def anomalies(zone: Annotated[list[str], typer.Option("--zone", "-z", help="une ou plusieurs zones")],
              first_year: Annotated[int, typer.Option("--from")] = 2015,
              last_year: Annotated[int, typer.Option("--to")] = 2024,
              element: Annotated[str, typer.Option(help="TMAX, TMIN ou PRCP")] = "TMAX",
              limit: int = 15, as_json: Json = False, show_explain: Explain = False) -> None:
    """F3 : mois les plus éloignés de la normale 1991-2020, classés."""
    if show_explain:
        show_plan(*f3_anomalies.query(zone, element, first_year, last_year))
    run(lambda c: f3_anomalies.anomalies(c, zone, element, first_year, last_year), as_json,
        lambda r: (table(f"Mois anormaux ({element}, anomalie en {r['unit']}, normale 1991-2020)", r["months"],
                         ["rank", "zone", "year", "month", "anomaly", "cells", "stations"], limit),
                   console.print("Sources d'un mois : trace --zone ZONE --element " + element +
                                 " --year AAAA --month MM")))


@app.command()
def events(start: Day, end: Day, zone: Zone = None, bbox: Bbox = None,
           element: Annotated[str, typer.Option(help="TMAX, TMIN ou PRCP")] = "TMAX",
           quantile: Annotated[float, typer.Option(help="seuil station x mois (1991-2020)")] = 0.95,
           min_cells: Annotated[int, typer.Option(help="mailles de 0,5° touchées au minimum")] = 3,
           min_share: Annotated[float, typer.Option(help="part minimale des mailles qui rapportent")] = 0.25,
           limit: int = 15, as_json: Json = False, show_explain: Explain = False) -> None:
    """F4 : événements régionaux (plusieurs mailles inhabituelles les mêmes jours) et extrêmes isolés."""
    a, s, e = area(zone, bbox), date.fromisoformat(start), date.fromisoformat(end)
    if show_explain:
        where, params = f4_regional.params_for(a, element, s, e, quantile)
        show_plan(f4_regional.SQL_THRESHOLDS.format(area=where), params)
        with connect() as conn:
            params = f4_regional.with_thresholds(conn, a, element, s, e, quantile)
        show_plan(f4_regional.SQL_DAILY, params)

    def show(r):
        table(f"{r['count']} événements régionaux ({element} > quantile {quantile} de la station)",
              [{**x, "evidence": len(x.get("evidence", []))} for x in r["events"]],
              ["start", "end", "days", "severity", "peak_date", "peak_share", "peak_cells_hit", "stations_hit",
               "evidence"], limit)
        iso = r["isolated"]
        table(f"Extrêmes isolés (une seule maille touchée) : {iso['days']} jours ; les plus marqués",
              [{**x, "stations": ", ".join(f"{v['station']} {v['value']}>{v['threshold']}"
                                          for v in x.get("evidence", []))} for x in iso["top"]],
              ["date", "cells_reporting", "stations_hit", "excess", "stations"], 5)
        console.print("Preuves complètes (station, date, valeur, seuil) : --json")
    run(lambda c: f4_regional.events(c, a, element, s, e, quantile, min_cells, min_share), as_json, show)


@app.command("trace")
def trace_cmd(station: str | None = None, zone: str | None = None, element: str | None = None,
              start: str | None = None, end: str | None = None, year: int | None = None, month: int | None = None,
              flagged_only: bool = False, limit: int = 50, as_json: Json = False) -> None:
    """Traçabilité : observations sources (station, date, élément, valeur, flags, lot)."""
    s = date.fromisoformat(start) if start else None
    e = date.fromisoformat(end) if end else None
    run(lambda c: trace.records(c, station, zone, element, s, e, year, month, flagged_only), as_json,
        lambda r: table(f"{r['count']} observations", r["records"],
                        ["station", "date", "element", "value", "mflag", "qflag", "sflag", "obs_time", "batch_id"],
                        limit))


@app.command("import")
def import_cmd(files: list[Path],
               years: Annotated[tuple[int, int] | None, typer.Option(help="limiter aux années")] = None) -> None:
    """F5 : importer un lot de fichiers NOAA (by_station ou by_year). Réimporter un lot ne change rien."""
    from ingest.load import import_files

    def compute(conn):
        return import_files(conn, files, tuple(years) if years else None, log=lambda m: console.print(m))
    run(compute, False, lambda r: console.print_json(json.dumps(r, default=str)))


if __name__ == "__main__":
    sys.exit(app())
