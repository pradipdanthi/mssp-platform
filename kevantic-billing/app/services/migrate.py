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
    "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS opportunity_id UUID REFERENCES opportunities(id)",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS opportunity_id UUID REFERENCES opportunities(id)",
    "ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS vendor_name VARCHAR(128)",
    "ALTER TABLE invoice_lines ADD COLUMN IF NOT EXISTS vendor_name VARCHAR(128)",
    "ALTER TABLE catalog_items ADD COLUMN IF NOT EXISTS vendor_name VARCHAR(128)",
    "UPDATE catalog_items SET vendor_name = 'NikTiar' WHERE vendor_name IS NULL AND sku LIKE 'NKT-%'",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS contact_title VARCHAR(128)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS estimated_budget NUMERIC(14, 2)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS salesperson_id UUID REFERENCES salespeople(id)",
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS salesperson_id UUID REFERENCES salespeople(id)",
    "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS requirement TEXT",
    "ALTER TABLE activities ADD COLUMN IF NOT EXISTS party_id UUID REFERENCES parties(id)",
    "ALTER TABLE activities ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES contacts(id)",
    # Lead status: earlier 'working' → Salesforce 'contacted'
    "UPDATE leads SET status = 'contacted' WHERE status = 'working'",
    # Opportunity stages → classic Salesforce pipeline
    "UPDATE opportunities SET stage = 'prospecting' WHERE stage IN ('qualification','assigned')",
    "UPDATE opportunities SET stage = 'needs_analysis' WHERE stage IN ('discovery','working','supplier_price')",
    "UPDATE opportunities SET stage = 'proposal' WHERE stage = 'proposal'",
    "UPDATE opportunities SET stage = 'negotiation' WHERE stage = 'negotiation'",
    "UPDATE opportunities SET stage = 'closed_won' WHERE stage IN ('commit','won','billed','paid','closed','closed_won')",
    "UPDATE opportunities SET stage = 'closed_lost' WHERE stage IN ('lost','closed_lost')",
]


def run_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in ALTERS:
            conn.execute(text(stmt))
