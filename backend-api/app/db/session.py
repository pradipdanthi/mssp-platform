"""
Database connection pool and helpers (psycopg_pool).

Drop-in replacement for the prior single-connection helpers. All existing
callers (fetch_all, fetch_one, execute, fetch_one_write, db_transaction)
keep the same signatures and semantics.

Pool is initialized once at module import; sizes are configurable via env.
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Tuple

import psycopg
import psycopg_pool
import redis
from psycopg.rows import dict_row


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


# ---------------------------------------------------------------------------
# Connection pool (module-level singleton)
# ---------------------------------------------------------------------------

_pool: psycopg_pool.ConnectionPool | None = None


def _get_pool() -> psycopg_pool.ConnectionPool:
    global _pool
    if _pool is None:
        conninfo = psycopg.conninfo.make_conninfo(
            host=_env("POSTGRES_HOST", "postgres"),
            port=_env("POSTGRES_PORT", "5432"),
            dbname=_env("POSTGRES_DB", "mssp_control"),
            user=_env("POSTGRES_USER", "mssp_admin"),
            password=_env("POSTGRES_PASSWORD"),
            connect_timeout="5",
        )
        _pool = psycopg_pool.ConnectionPool(
            conninfo=conninfo,
            min_size=int(_env("DB_POOL_MIN_SIZE", "5")),
            max_size=int(_env("DB_POOL_MAX_SIZE", "20")),
            max_idle=300.0,
            timeout=float(_env("DB_POOL_TIMEOUT", "30")),
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


# ---------------------------------------------------------------------------
# Public helpers (same API as before — no caller changes needed)
# ---------------------------------------------------------------------------

@contextmanager
def db_conn():
    """Yield a connection from the pool (auto-returned on exit)."""
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


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


def fetch_one_write(query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any]:
    """Execute a write statement with RETURNING and commit."""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {}


@contextmanager
def db_transaction():
    """
    Yield a cursor for multi-statement transactions.
    Commits on clean exit; rolls back on exception.
    """
    with db_conn() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Redis helper (unchanged)
# ---------------------------------------------------------------------------

def redis_client() -> redis.Redis:
    return redis.Redis(
        host=_env("REDIS_HOST", "redis"),
        port=int(_env("REDIS_PORT", "6379")),
        password=_env("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
