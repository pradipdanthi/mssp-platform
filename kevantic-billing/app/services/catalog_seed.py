"""NikTiar portfolio catalog — list prices (editable). Aligned to PRODUCT_TIER_SOURCE_OF_TRUTH + SecureEdge."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CatalogItem

# List prices in INR — commercial defaults for quoting; change in UI/API as needed.
# Subscription prices are monthly per unit; quote engine multiplies by term_months.
SEED: list[dict] = [
    {
        "sku": "NKT-SILVER-EP",
        "name": "NikTiar Silver — Endpoint Detection & Response",
        "description": (
            "Managed EDR, SOC monitoring, alert triage, monthly reporting. "
            "Per protected endpoint / month."
        ),
        "product_family": "subscription_tier",
        "billing_model": "subscription",
        "unit_label": "endpoint / month",
        "list_price": Decimal("499.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998313",
        "min_qty": 25,
        "sort_order": 10,
    },
    {
        "sku": "NKT-GOLD-EP",
        "name": "NikTiar Gold — Advanced Detection & Response",
        "description": (
            "Everything in Silver plus deeper investigation, priority response, "
            "vulnerability visibility. Per protected endpoint / month."
        ),
        "product_family": "subscription_tier",
        "billing_model": "subscription",
        "unit_label": "endpoint / month",
        "list_price": Decimal("899.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998313",
        "min_qty": 25,
        "sort_order": 20,
    },
    {
        "sku": "NKT-PLATINUM-EP",
        "name": "NikTiar Platinum — Full MDR / XDR Suite",
        "description": (
            "Everything in Gold plus case management orchestration, threat intel "
            "enrichment, dedicated analyst attention. Per protected endpoint / month."
        ),
        "product_family": "subscription_tier",
        "billing_model": "subscription",
        "unit_label": "endpoint / month",
        "list_price": Decimal("1499.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998313",
        "min_qty": 25,
        "sort_order": 30,
    },
    {
        "sku": "NKT-SE-SHARED-HOST",
        "name": "NikTiar SecureEdge — Shared Edge",
        "description": (
            "Managed Secure Edge protection for public hostnames: WAF, bot mitigation, "
            "DDoS posture, TLS edge, origin shielding. Per hostname / month."
        ),
        "product_family": "secure_edge",
        "billing_model": "subscription",
        "unit_label": "hostname / month",
        "list_price": Decimal("2999.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998313",
        "min_qty": 1,
        "sort_order": 40,
    },
    {
        "sku": "NKT-SE-DEDICATED",
        "name": "NikTiar SecureEdge — Dedicated Edge",
        "description": (
            "Dedicated Secure Edge capacity and policy plane for regulated or "
            "high-traffic estates. Flat monthly."
        ),
        "product_family": "secure_edge",
        "billing_model": "subscription",
        "unit_label": "estate / month",
        "list_price": Decimal("49999.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998313",
        "min_qty": 1,
        "sort_order": 50,
    },
    {
        "sku": "NKT-EDGE-NODE",
        "name": "NikTiar Edge Node Appliance",
        "description": (
            "On-premises edge appliance for hybrid SecureEdge / sensor forwarding. "
            "One-time hardware + software license."
        ),
        "product_family": "appliance",
        "billing_model": "one_time",
        "unit_label": "appliance",
        "list_price": Decimal("175000.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "84715000",
        "min_qty": 1,
        "sort_order": 60,
    },
    {
        "sku": "NKT-ONBOARD-PKG",
        "name": "Professional Onboarding Package",
        "description": (
            "Guided tenant onboarding, agent rollout planning, SecureEdge hostname "
            "cutover assistance, and first-month SOC runbook alignment."
        ),
        "product_family": "professional_services",
        "billing_model": "one_time",
        "unit_label": "engagement",
        "list_price": Decimal("75000.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998314",
        "min_qty": 1,
        "sort_order": 70,
    },
    {
        "sku": "NKT-RETAINER-STD",
        "name": "SOC Advisory Retainer (Standard)",
        "description": "Monthly advisory hours for tabletop, policy review, and executive briefings.",
        "product_family": "professional_services",
        "billing_model": "subscription",
        "unit_label": "retainer / month",
        "list_price": Decimal("45000.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "998314",
        "min_qty": 1,
        "sort_order": 80,
    },
]


def seed_catalog(db: Session) -> int:
    created = 0
    for item in SEED:
        existing = db.query(CatalogItem).filter(CatalogItem.sku == item["sku"]).one_or_none()
        if existing:
            continue
        db.add(
            CatalogItem(
                sku=item["sku"],
                name=item["name"],
                description=item["description"],
                product_family=item["product_family"],
                billing_model=item["billing_model"],
                unit_label=item["unit_label"],
                list_price=item["list_price"],
                currency="INR",
                gst_rate=item["gst_rate"],
                hsn_sac=item["hsn_sac"],
                min_qty=item["min_qty"],
                active=True,
                sort_order=item["sort_order"],
            )
        )
        created += 1
    if created:
        db.commit()
    return created
