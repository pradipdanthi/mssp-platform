"""Tally-inspired tax invoice / quote PDF generator."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import get_settings


def _money(v) -> str:
    return f"{float(v):,.2f}"


def render_document_pdf(
    *,
    doc_title: str,
    doc_number: str,
    party_name: str,
    party_address: str | None,
    party_gstin: str | None,
    party_state: str | None,
    issue_date: str,
    due_or_valid: str | None,
    tax_mode: str,
    lines: list[dict],
    subtotal,
    discount_amount,
    taxable_amount,
    cgst_amount,
    sgst_amount,
    igst_amount,
    total_amount,
    currency: str,
    notes: str | None = None,
) -> bytes:
    settings = get_settings()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleKEV",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#0f2744"),
        spaceAfter=4,
    )
    small = ParagraphStyle("SmallKEV", parent=styles["Normal"], fontSize=9, leading=12)

    story = []
    story.append(Paragraph(settings.company_name, title_style))
    story.append(
        Paragraph(
            f"{settings.company_address}<br/>"
            f"State: {settings.company_state} ({settings.company_state_code}) &nbsp;|&nbsp; "
            f"GSTIN: {settings.company_gstin or '—'}<br/>"
            f"<b>{doc_title}</b> &nbsp; {doc_number}",
            small,
        )
    )
    story.append(Spacer(1, 8))

    bill_to = (
        f"<b>Bill To</b><br/>{party_name}<br/>"
        f"{(party_address or '').replace(chr(10), '<br/>')}<br/>"
        f"State: {party_state or '—'} &nbsp;|&nbsp; GSTIN: {party_gstin or '—'}<br/>"
        f"Issue date: {issue_date}"
        + (f"<br/>{due_or_valid}" if due_or_valid else "")
        + f"<br/>Tax mode: {tax_mode.upper().replace('_', ' ')} &nbsp;|&nbsp; Currency: {currency}"
    )
    story.append(Paragraph(bill_to, small))
    story.append(Spacer(1, 10))

    header = ["#", "SKU / Description", "HSN", "Qty", "Rate", "Taxable", "Tax", "Total"]
    data = [header]
    for i, ln in enumerate(lines, start=1):
        data.append(
            [
                str(i),
                f"{ln['sku']}\n{ln['description']}"[:80],
                ln.get("hsn_sac") or "—",
                _money(ln["quantity"]),
                _money(ln["unit_price"]),
                _money(ln["line_taxable"]),
                _money(ln["line_tax"]),
                _money(ln["line_total"]),
            ]
        )

    table = Table(data, colWidths=[18, 170, 45, 40, 55, 55, 50, 55])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2744")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5d0dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))

    totals_rows = [
        ["Subtotal", _money(subtotal)],
        ["Discount", _money(discount_amount)],
        ["Taxable value", _money(taxable_amount)],
        ["CGST", _money(cgst_amount)],
        ["SGST", _money(sgst_amount)],
        ["IGST", _money(igst_amount)],
        ["Grand Total", f"{currency} {_money(total_amount)}"],
    ]
    totals = Table(totals_rows, colWidths=[120, 100], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0f2744")),
            ]
        )
    )
    story.append(totals)

    if notes:
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"<b>Notes</b><br/>{notes}", small))

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "This is a computer-generated tax document from Kevantic Quote & Billing. "
            "Subject to the commercial terms in the related quotation / MSA.",
            small,
        )
    )

    doc.build(story)
    return buf.getvalue()
