"""
KB-010: Database connection helper for the new auth module.

This is a deliberately self-contained copy of the same connection pattern
already used in app/main.py (same environment variables, same parameterized
query style). It is kept separate on purpose so that the new auth code has
zero risk of changing behavior for the existing, already-validated
endpoints in main.py - main.py's own database helpers are untouched.
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Tuple

import psycopg
from psycopg.rows import dict_row


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@contextmanager
def db_conn():
    conn = psycopg.connect(
        host=_env("POSTGRES_HOST", "postgres"),
        port=int(_env("POSTGRES_PORT", "5432")),
        dbname=_env("POSTGRES_DB", "mssp_control"),
        user=_env("POSTGRES_USER", "mssp_admin"),
        password=_env("POSTGRES_PASSWORD"),
        row_factory=dict_row,
        connect_timeout=5,
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())


def fetch_one(query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any]:
    rows = fetch_all(query, params)
    if not rows:
        return {}
    return rows[0]


def execute(query: str, params: Tuple[Any, ...] = ()) -> None:
    """Run a write statement (INSERT/UPDATE) and commit it."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
