"""Comparaison automatique : le même service doit donner le même résultat en local et sur Citus.

Usage : uv run pytest tests/test_local_vs_citus.py -v
Les deux bases doivent contenir les mêmes observations (même chargement) :
  LOCAL_URL (défaut : localhost:5440) et CITUS_URL (défaut : coordinateur localhost:5441).
Les résultats sont comparés après sérialisation JSON canonique (clés triées) ; les services
renvoient déjà leurs listes dans un ordre canonique (égalités départagées par station puis date).
Les cas couvrent des stations sur des workers différents et des zones qui s'étendent sur tous les workers.
"""

import json
import os
from datetime import date
from pathlib import Path

import psycopg
import pytest

from ingest.load import import_files
from weatherscope.db import connect
from weatherscope.services import f1_station, f2_episodes, f3_anomalies, f4_regional, trace
from weatherscope.services.common import Area, tenths

LOCAL_URL = os.environ.get("LOCAL_URL", "postgresql://weatherscope:weatherscope@localhost:5440/weatherscope")
CITUS_URL = os.environ.get("CITUS_URL", "postgresql://weatherscope:weatherscope@localhost:5441/weatherscope")
ROOT = Path(__file__).resolve().parent.parent


def canonical(result: dict) -> str:
    return json.dumps(result, sort_keys=True, ensure_ascii=False, default=str)


@pytest.fixture(scope="module")
def local():
    try:
        with connect(LOCAL_URL) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        pytest.skip(f"base locale indisponible : {exc}")


@pytest.fixture(scope="module")
def citus():
    try:
        with connect(CITUS_URL) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        pytest.skip(f"coordinateur Citus indisponible : {exc}")


@pytest.fixture(scope="module")
def stations_by_worker(citus) -> dict[str, list[str]]:
    """Quelques stations de chaque worker (d'après le placement réel des shards)."""
    with citus.cursor() as cur:
        cur.execute("""SELECT cs.nodename, s.id FROM stations s
                       JOIN citus_shards cs ON cs.shardid = get_shard_id_for_distribution_column('observations', s.id)
                       WHERE cs.table_name = 'observations'::regclass ORDER BY 1, 2""")
        out: dict[str, list[str]] = {}
        for node, sid in cur.fetchall():
            out.setdefault(node, []).append(sid)
    assert len(out) >= 2, "les observations doivent être réparties sur au moins 2 workers"
    return {node: ids[::max(1, len(ids) // 3)][:3] for node, ids in out.items()}


def assert_same(a: dict, b: dict) -> None:
    ca, cb = canonical(a), canonical(b)
    assert ca == cb, f"résultats différents ({len(ca)} contre {len(cb)} caractères)"


def test_les_donnees_sont_reparties_et_identiques(local, citus):
    counts = []
    for conn in (local, citus):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), count(DISTINCT station), min(date), max(date), sum(value) FROM observations")
            counts.append(cur.fetchone())
    assert counts[0] == counts[1], f"jeux de données différents : {counts}"
    with citus.cursor() as cur:  # réparti, pas copié : chaque worker garde une partie seulement
        cur.execute("SELECT count(DISTINCT nodename) FROM citus_shards WHERE table_name = 'observations'::regclass")
        assert cur.fetchone()[0] >= 2


@pytest.mark.parametrize("period", [(date(2015, 1, 1), date(2024, 12, 31)), (date(1991, 1, 1), date(2024, 12, 31))])
def test_f1_stations_de_chaque_worker(local, citus, stations_by_worker, period):
    for node, ids in stations_by_worker.items():
        for sid in ids:
            assert_same(f1_station.summary(local, sid, *period), f1_station.summary(citus, sid, *period)), node


def test_f1_recherche_de_stations(local, citus):
    for area in (Area(zones=["SP"]), Area(zones=["GM"]), Area(bbox=(47.0, 50.0, 7.0, 11.0))):
        assert_same(f1_station.search(local, area), f1_station.search(citus, area))


@pytest.mark.parametrize("zones,element,threshold,min_days", [
    (["SP"], "TMAX", 40.0, 3),     # chaleur, une zone
    (["GM"], "PRCP", 10.0, 2),     # pluie, une autre zone
    (["GM", "SP"], "TMIN", 22.0, 3),  # deux zones : tous les workers sont contactés
])
def test_f2_episodes(local, citus, zones, element, threshold, min_days):
    args = (Area(zones=zones), element, date(2015, 1, 1), date(2024, 12, 31), tenths(threshold), min_days)
    a, b = f2_episodes.episodes(local, *args), f2_episodes.episodes(citus, *args)
    assert a["count"] > 0, "cas sans épisode : le test ne prouverait rien"
    assert_same(a, b)


def test_f2_episode_a_cheval_sur_deux_annees_identique(local, citus):
    args = (Area(zones=["GM"]), "PRCP", date(2018, 1, 1), date(2019, 12, 31), tenths(5.0), 3)
    a, b = f2_episodes.episodes(local, *args), f2_episodes.episodes(citus, *args)
    assert any(e["start"][:4] != e["end"][:4] for e in json.loads(canonical(a))["episodes"])
    assert_same(a, b)


@pytest.mark.parametrize("zones,element", [(["GM"], "TMAX"), (["SP"], "PRCP"), (["GM", "SP"], "TMIN")])
def test_f3_anomalies(local, citus, zones, element):
    a, b = f3_anomalies.anomalies(local, zones, element, 2015, 2024), f3_anomalies.anomalies(citus, zones, element, 2015, 2024)
    assert a["months"], "classement vide"
    assert_same(a, b)


def test_f4_evenements_regionaux(local, citus):
    args = (Area(zones=["SP"]), "PRCP", date(2018, 1, 1), date(2024, 12, 31))
    assert_same(f4_regional.events(local, *args), f4_regional.events(citus, *args))


def test_trace_station_et_zone(local, citus):
    assert_same(trace.records(local, station="SPE00120503", element="TMAX", start=date(2022, 7, 7), end=date(2022, 7, 17)),
                trace.records(citus, station="SPE00120503", element="TMAX", start=date(2022, 7, 7), end=date(2022, 7, 17)))
    assert_same(trace.records(local, zone="GM", element="TMAX", year=2021, month=7),
                trace.records(citus, zone="GM", element="TMAX", year=2021, month=7))


def test_f5_reimporter_un_lot_ne_change_rien(local, citus):
    """Réimporter un fichier déjà chargé : 0 nouvelle, 0 modifiée, archive inchangée, sur les deux déploiements."""
    files = [ROOT / "data" / "raw" / "by_station" / "SPE00120503.csv.gz"]
    for conn in (local, citus):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), sum(value), (SELECT count(*) FROM observations_history) FROM observations")
            before = cur.fetchone()
        counts = import_files(conn, files, (1991, 2024), log=lambda _: None)  # mêmes années que le chargement initial
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), sum(value), (SELECT count(*) FROM observations_history) FROM observations")
            after = cur.fetchone()
        assert counts["inserted"] == 0 and counts["updated"] == 0 and counts["read"] > 0
        assert before == after
