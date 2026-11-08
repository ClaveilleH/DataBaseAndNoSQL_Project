"""Interface web (D28) : l'API renvoie exactement les résultats des services, et échoue explicitement.

Base : DATABASE_URL (par défaut le local, 127.0.0.1:5440) ; tests ignorés si elle ne répond pas.
"""

import json
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from weatherscope.db import connect
from weatherscope.services import f2_episodes, f3_anomalies
from weatherscope.services.common import Area, tenths
from weatherscope.web.app import app


@pytest.fixture(scope="module")
def conn():
    try:
        with connect() as c:
            yield c
    except psycopg.OperationalError as exc:  # base absente : rien à tester
        pytest.skip(f"base indisponible : {exc}")


@pytest.fixture(scope="module")
def client(conn):
    return TestClient(app)


def same(a, b) -> None:
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_page_et_info(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/info").json()["stations"] == 774


def test_f2_identique_au_service(client, conn):
    r = client.get("/api/episodes", params={"zone": "SP", "start": "2015-01-01", "end": "2024-12-31", "threshold": 40})
    same(r.json(), f2_episodes.episodes(conn, Area(zones=["SP"]), "TMAX", date(2015, 1, 1), date(2024, 12, 31),
                                        tenths(40), 3))


def test_f3_identique_au_service(client, conn):
    r = client.get("/api/anomalies", params={"zone": ["GM", "SP"], "element": "PRCP"})
    same(r.json(), f3_anomalies.anomalies(conn, ["GM", "SP"], "PRCP", 2015, 2024))


def test_erreurs_explicites(client):
    assert client.get("/api/station/INCONNUE", params={"start": "2022-01-01", "end": "2022-01-31"}).status_code == 404
    assert client.get("/api/episodes", params={"start": "2022-01-01", "end": "2022-12-31", "threshold": 40}).status_code == 422
    assert client.get("/api/anomalies", params={"zone": "GM", "element": "SNOW"}).status_code == 422


def test_base_indisponible(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://weatherscope:weatherscope@127.0.0.1:1/weatherscope")
    r = TestClient(app).get("/api/anomalies", params={"zone": "GM"})
    assert r.status_code == 503
    assert r.json()["detail"].startswith("ÉCHEC") and "Aucun résultat partiel" in r.json()["detail"]
