"""Sample sales team and customers for the Salesforce-style cycle.

All sample rows use TEST — in the name so they are obvious.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Activity, Contact, Lead, Opportunity, Party, Salesperson, SupplierPrice
from app.services import numbering, quote_engine


TEAM = (
    ("rahul.desai@kevantic.example", "Rahul Desai", "manager", "9800000101"),
    ("priya.shah@kevantic.example", "Priya Shah", "bdc", "9800000102"),
    ("arjun.mehta@kevantic.example", "Arjun Mehta", "bde", "9800000103"),
    ("neha.kulkarni@kevantic.example", "Neha Kulkarni", "bde", "9800000104"),
)


def _person(db: Session, email: str, name: str, role: str, phone: str) -> Salesperson:
    row = db.query(Salesperson).filter(Salesperson.email == email).one_or_none()
    if row:
        return row
    row = Salesperson(name=name, role=role, email=email, phone=phone, active=True)
    db.add(row)
    db.flush()
    return row


def seed_sales_showcase(db: Session) -> None:
    people = {
        email: _person(db, email, name, role, phone) for email, name, role, phone in TEAM
    }
    priya = people["priya.shah@kevantic.example"]
    arjun = people["arjun.mehta@kevantic.example"]
    neha = people["neha.kulkarni@kevantic.example"]
    db.commit()

    if not db.query(Lead).filter(Lead.company_name == "TEST — Harbor Textiles").one_or_none():
        lead = Lead(
            lead_number=numbering.next_lead_number(db),
            company_name="TEST — Harbor Textiles",
            contact_name="Rakesh Jain",
            contact_title="Purchase manager",
            email="rakesh.jain@harbor.example",
            phone="9800000201",
            source="Website",
            interest="20 business laptops for the accounts team",
            status="contacted",
            salesperson_id=priya.id,
            owner=priya.name,
            notes="Sample lead. BDC is qualifying. Not converted yet.",
        )
        db.add(lead)
        db.flush()
        db.add(
            Activity(
                lead_id=lead.id,
                kind="call",
                subject="Spoke to Rakesh. Spec list coming tomorrow.",
                owner=priya.name,
                done=True,
            )
        )
        db.commit()

    if not db.query(Party).filter(Party.legal_name == "TEST — Brightpath Hospitals").one_or_none():
        party = Party(
            legal_name="TEST — Brightpath Hospitals",
            display_name="Brightpath Hospitals",
            email="meera.iyer@brightpath.example",
            phone="9800000301",
            billing_address="Sample address, Pune",
            state="Maharashtra",
            state_code="27",
            notes="Sample Account with an open Opportunity.",
        )
        db.add(party)
        db.flush()
        contact = Contact(
            party_id=party.id,
            name="Meera Iyer",
            title="IT head",
            email=party.email,
            phone=party.phone,
            is_primary=True,
        )
        db.add(contact)
        db.flush()
        lead = Lead(
            lead_number=numbering.next_lead_number(db),
            company_name=party.legal_name,
            contact_name=contact.name,
            contact_title=contact.title,
            email=contact.email,
            phone=contact.phone,
            source="Referral",
            interest="Firewall and 24 access switches for the new wing",
            status="converted",
            salesperson_id=priya.id,
            owner=priya.name,
            party_id=party.id,
        )
        db.add(lead)
        db.flush()
        opp = Opportunity(
            opportunity_number=numbering.next_opportunity_number(db),
            name="TEST — Brightpath Hospitals — firewall and switches",
            party_id=party.id,
            contact_id=contact.id,
            lead_id=lead.id,
            stage="needs_analysis",
            source="Referral",
            salesperson_id=arjun.id,
            owner=arjun.name,
            requirement="Firewall and 24 access switches for the new wing",
            amount_expected=Decimal("650000"),
            probability=25,
            next_step="Choose distributor price and generate customer quote",
            close_date=date.today() + timedelta(days=21),
        )
        db.add(opp)
        db.flush()
        db.add_all(
            [
                Activity(
                    opportunity_id=opp.id,
                    party_id=party.id,
                    contact_id=contact.id,
                    kind="meeting",
                    subject="Site visit — requirement confirmed",
                    owner=arjun.name,
                    done=True,
                ),
                SupplierPrice(
                    opportunity_id=opp.id,
                    supplier_name="Redington",
                    supplier_kind="distributor",
                    item_name="FortiGate 80F firewall",
                    sku="FG-80F",
                    quantity=Decimal("1"),
                    unit_cost=Decimal("84500"),
                    sell_unit_price=Decimal("99000"),
                    gst_rate=Decimal("18"),
                    quote_ref="RED-88921",
                    valid_until=date.today() + timedelta(days=15),
                    status="chosen",
                ),
                SupplierPrice(
                    opportunity_id=opp.id,
                    supplier_name="Cisco",
                    supplier_kind="oem",
                    item_name="24-port access switch",
                    sku="C9200-24",
                    quantity=Decimal("24"),
                    unit_cost=Decimal("18500"),
                    gst_rate=Decimal("18"),
                    quote_ref="CSC-2208",
                    valid_until=date.today() + timedelta(days=20),
                    status="received",
                ),
            ]
        )
        db.commit()

    if db.query(Party).filter(Party.legal_name == "TEST — Saffron Retail").one_or_none():
        return

    party = Party(
        legal_name="TEST — Saffron Retail",
        display_name="Saffron Retail",
        email="anil@saffron.example",
        phone="9800000401",
        billing_address="Sample address, Pune",
        state="Maharashtra",
        state_code="27",
        notes="Sample Account. Opportunity already Closed Won and paid.",
    )
    db.add(party)
    db.flush()
    contact = Contact(
        party_id=party.id,
        name="Anil Kulkarni",
        title="Director",
        email=party.email,
        phone=party.phone,
        is_primary=True,
    )
    db.add(contact)
    db.flush()
    lead = Lead(
        lead_number=numbering.next_lead_number(db),
        company_name=party.legal_name,
        contact_name=contact.name,
        contact_title=contact.title,
        email=contact.email,
        phone=contact.phone,
        source="Existing customer",
        interest="10 barcode scanners for the new store",
        status="converted",
        salesperson_id=neha.id,
        owner=neha.name,
        party_id=party.id,
    )
    db.add(lead)
    db.flush()
    opp = Opportunity(
        opportunity_number=numbering.next_opportunity_number(db),
        name="TEST — Saffron Retail — barcode scanners",
        party_id=party.id,
        contact_id=contact.id,
        lead_id=lead.id,
        stage="prospecting",
        source="Existing customer",
        salesperson_id=neha.id,
        owner=neha.name,
        requirement="10 barcode scanners for the new store",
        customer_po="PO-SAF-1044",
        probability=10,
    )
    db.add(opp)
    db.flush()
    db.add(
        SupplierPrice(
            opportunity_id=opp.id,
            supplier_name="Ingram Micro",
            supplier_kind="distributor",
            item_name="Honeywell barcode scanner",
            sku="HH-1900",
            quantity=Decimal("10"),
            unit_cost=Decimal("4200"),
            sell_unit_price=Decimal("5600"),
            gst_rate=Decimal("18"),
            quote_ref="ING-55210",
            status="chosen",
        )
    )
    db.commit()
    quote = quote_engine.build_quote(
        db,
        party=party,
        line_specs=[
            {
                "sku": "HH-1900",
                "description": "Honeywell barcode scanner (Ingram Micro ING-55210)",
                "vendor_name": "Ingram Micro",
                "quantity": Decimal("10"),
                "unit_price": Decimal("5600"),
                "gst_rate": Decimal("18"),
                "billing_model": "one_time",
            }
        ],
        opportunity_id=opp.id,
        opportunity_name=opp.name,
        sales_owner=neha.name,
        notes="Sample closed-won requirement.",
    )
    invoice = quote_engine.accept_quote_to_invoice(db, quote, invoice_type="tax_invoice")
    quote_engine.record_payment(
        db,
        invoice,
        amount=invoice.total_amount,
        method="bank_transfer",
        reference="TEST-NEFT-1001",
        notes="Sample payment",
    )
    finished = db.get(Opportunity, opp.id)
    if finished:
        finished.stage = "closed_won"
        finished.probability = 100
        finished.amount_expected = invoice.total_amount
        finished.next_step = "Closed Won. Account stays for the next requirement."
        db.add(
            Activity(
                opportunity_id=finished.id,
                party_id=party.id,
                contact_id=contact.id,
                kind="note",
                subject="Opportunity Closed Won — billed and paid",
                body="Sales cycle finished for this requirement. Account remains.",
                owner=neha.name,
                done=True,
            )
        )
        db.commit()
