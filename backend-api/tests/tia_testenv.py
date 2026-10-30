"""Shared setup guards for the TIA test suites.

A missing dependency or database must FAIL the run, never skip it silently:
a skipped routing test looks like a pass. Set TIA_ALLOW_SKIP_TESTS=1 only for a
deliberate partial run (for example a laptop with no Postgres); the runner script
``scripts/tia_local_test.sh`` never sets it.
"""

from __future__ import annotations

import importlib.util
import os
import unittest

REQUIRED_TEST_MODULES = ("httpx",)


def skips_allowed() -> bool:
    return os.getenv("TIA_ALLOW_SKIP_TESTS") == "1"


def database_ready() -> bool:
    try:
        from app.db.session import fetch_one

        row = fetch_one("SELECT to_regclass('public.tia_notifications') AS t;")
        return bool(row and row.get("t"))
    except Exception:
        return False


def require_database() -> None:
    """Call from setUpClass. Fails (or skips only when explicitly allowed)."""
    if database_ready():
        return
    message = (
        "TIA tests need Postgres initialised from postgres/init (migrations 117 and 118). "
        "Run scripts/tia_local_test.sh, or set TIA_ALLOW_SKIP_TESTS=1 for a deliberate partial run."
    )
    if skips_allowed():
        raise unittest.SkipTest(message)
    raise RuntimeError(message)


def missing_test_modules() -> list:
    return [m for m in REQUIRED_TEST_MODULES if importlib.util.find_spec(m) is None]


def require_test_modules() -> None:
    missing = missing_test_modules()
    if not missing:
        return
    message = (
        "missing test dependencies: " + ", ".join(missing)
        + " (install backend-api/requirements-test.txt; scripts/tia_local_test.sh builds an image that has them)"
    )
    if skips_allowed():
        raise unittest.SkipTest(message)
    raise RuntimeError(message)
