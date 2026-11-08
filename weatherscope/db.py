"""Connexion PostgreSQL commune (contrat partagé : voir CLAUDE.md).

Le même code sert en local et en distribué : seule la variable DATABASE_URL change
(serveur PostgreSQL local ou coordinateur Citus).
"""

import os

import psycopg

DEFAULT_URL = "postgresql://weatherscope:weatherscope@localhost:5440/weatherscope"


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or os.environ.get("DATABASE_URL", DEFAULT_URL))
