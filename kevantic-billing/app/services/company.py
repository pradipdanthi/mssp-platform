from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CompanyProfile

DEFAULT_TERMS = (
    "1. Prices are in INR exclusive of applicable GST unless stated.\n"
    "2. Subscription fees are billed for the full quote term upfront unless agreed otherwise.\n"
    "3. Payment due as per invoice due date; late payments may pause managed services.\n"
    "4. SecureEdge hostname onboarding requires DNS cutover windows mutually agreed.\n"
    "5. This quotation is confidential and valid until the stated expiry date."
)


def get_or_create_profile(db: Session) -> CompanyProfile:
    row = db.get(CompanyProfile, 1)
    if row:
        return row
    s = get_settings()
    row = CompanyProfile(
        id=1,
        legal_name=s.company_name,
        gstin=s.company_gstin or None,
        state=s.company_state,
        state_code=s.company_state_code,
        address=s.company_address,
        currency=s.default_currency,
        lut_filed=s.lut_filed,
        quote_validity_days=s.quote_validity_days,
        default_terms=DEFAULT_TERMS,
        invoice_footer=(
            "Computer-generated tax document from Kevantic Quote & Billing. "
            "Subject to MSA / quotation terms."
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
