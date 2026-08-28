"""
Database connection pool and helpers (psycopg_pool).

Drop-in replacement for the prior single-connection helpers. All existing
callers (fetch_all, fetch_one, execute, fetch_one_write, db_transaction)
keep the same signatures and semantics.

Pool is initialized once at module import; sizes are configurable via env.

RLS: set ``app.current_tenant`` / ``app.current_role`` per transaction via
``set_db_session_context()`` (typically from ``get_current_user``).
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional, Tuple

import psycopg
import psycopg_pool
import redis
from psycopg.rows import dict_row

SOC_BYPASS_ROLES = frozenset({"platform_admin", "soc_manager", "soc_analyst"})

_current_tenant: ContextVar[Optional[str]] = ContextVar("db_current_tenant", default=None)
_current_role: ContextVar[Optional[str]] = ContextVar("db_current_role", default=None)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def set_db_session_context(
    *,
    tenant_id: Optional[str] = None,
    role: Optional[str] = None,
) -> Tuple[Token, Token]:
    """Bind tenant/role for RLS GUCs on subsequent DB operations in this context."""
    tenant_token = _current_tenant.set((tenant_id or "").strip() or None)
    role_token = _current_role.set((role or "").strip() or None)
    return tenant_token, role_token


def reset_db_session_context(tokens: Tuple[Token, Token]) -> None:
    """Restore prior RLS context tokens (request teardown)."""
    tenant_token, role_token = tokens
    _current_tenant.reset(tenant_token)
    _current_role.reset(role_token)


def bind_db_session_context_from_user(user: Dict[str, Any]) -> None:
    """
    Map an authenticated user row to RLS session variables.

    Customer roles scope to their tenant_id. SOC roles bypass via app.current_role.
    """
    role = str(user.get("role") or "").strip() or None
    tenant_id = user.get("tenant_id")
    if role in SOC_BYPASS_ROLES:
        set_db_session_context(tenant_id=None, role=role)
        return
    if role in ("customer_admin", "customer_viewer") and tenant_id:
        set_db_session_context(tenant_id=str(tenant_id), role=role)
        return
    set_db_session_context(tenant_id=None, role=role)


def _apply_rls_config(cur) -> None:
    """SET LOCAL GUCs consumed by postgres RLS policies (042_enable_rls.sql)."""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'mssp_app'")
    if cur.fetchone():
        # Superusers bypass RLS; enforce tenant policies via non-superuser app role.
        cur.execute("SET LOCAL ROLE mssp_app")
    tenant = _current_tenant.get() or ""
    role = _current_role.get() or ""
    cur.execute(
        "SELECT set_config('app.current_tenant', %s, true), "
        "set_config('app.current_role', %s, true)",
        (tenant, role),
    )


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
        with conn.transaction():
            with conn.cursor() as cur:
                _apply_rls_config(cur)
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
        with conn.transaction():
            with conn.cursor() as cur:
                _apply_rls_config(cur)
                cur.execute(query, params)


def fetch_one_write(query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any]:
    """Execute a write statement with RETURNING and commit."""
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _apply_rls_config(cur)
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else {}


@contextmanager
def db_transaction():
    """
    Yield a cursor for multi-statement transactions.
    Commits on clean exit; rolls back on exception.
    """
    with db_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                _apply_rls_config(cur)
                yield cur


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
