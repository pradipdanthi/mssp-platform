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
import redis
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


# KB-013: minimal addition for INSERT/UPDATE ... RETURNING ... statements
# that need the resulting row back (e.g. admin tenant create/update).
# execute() above intentionally doesn't return anything, and fetch_all()/
# fetch_one() intentionally don't commit - this is the one write helper
# that does both, added rather than changing either existing function's
# behavior.
def fetch_one_write(query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


# KB-012: moved from app/main.py, unchanged, so app/api/routes/health.py (and
# any other future module) has one shared place to get a Redis client from,
# instead of each route file defining its own copy.
def redis_client() -> redis.Redis:
    return redis.Redis(
        host=_env("REDIS_HOST", "redis"),
        port=int(_env("REDIS_PORT", "6379")),
        password=_env("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
