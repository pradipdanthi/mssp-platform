"""Additive column migrations for existing billing DBs (create_all alone won't ALTER)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


ALTERS = [
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS terms_text TEXT",
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS opportunity_name VARCHAR(255)",
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS sales_owner VARCHAR(128)",
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS requires_approval BOOLEAN DEFAULT FALSE",
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS approved_by VARCHAR(128)",
]


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in ALTERS:
            conn.execute(text(stmt))
