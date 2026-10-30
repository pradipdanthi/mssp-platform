"""Tally-inspired tax invoice / quote PDF generator."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
    terms: str | None = None,
    company=None,
    opportunity: str | None = None,
    amount_paid=None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleKEV",
        parent=styles["Heading1"],
        fontSize=15,
        textColor=colors.HexColor("#0f2744"),
        spaceAfter=2,
    )
    small = ParagraphStyle("SmallKEV", parent=styles["Normal"], fontSize=8.5, leading=11)

    co_name = getattr(company, "legal_name", None) or "Kevantic"
    co_addr = getattr(company, "address", None) or ""
    co_state = getattr(company, "state", None) or ""
    co_code = getattr(company, "state_code", None) or ""
    co_gstin = getattr(company, "gstin", None) or "—"
    co_email = getattr(company, "email", None) or ""
    co_phone = getattr(company, "phone", None) or ""

    story = []
    story.append(Paragraph(co_name, title_style))
    story.append(
        Paragraph(
            f"{co_addr}<br/>"
            f"State: {co_state} ({co_code}) &nbsp;|&nbsp; GSTIN: {co_gstin}"
            + (f" &nbsp;|&nbsp; {co_email}" if co_email else "")
            + (f" &nbsp;|&nbsp; {co_phone}" if co_phone else "")
            + f"<br/><b>{doc_title}</b> &nbsp; {doc_number}"
            + (f"<br/>Opportunity: {opportunity}" if opportunity else ""),
            small,
        )
    )
    story.append(Spacer(1, 6))

    bill_to = (
        f"<b>Bill To</b><br/>{party_name}<br/>"
        f"{(party_address or '').replace(chr(10), '<br/>')}<br/>"
        f"State: {party_state or '—'} &nbsp;|&nbsp; GSTIN: {party_gstin or '—'}<br/>"
        f"Issue date: {issue_date}"
        + (f"<br/>{due_or_valid}" if due_or_valid else "")
        + f"<br/>Tax mode: {tax_mode.upper().replace('_', ' ')} &nbsp;|&nbsp; Currency: {currency}"
    )
    story.append(Paragraph(bill_to, small))
    story.append(Spacer(1, 8))

    header = ["#", "SKU / Description", "HSN", "Qty", "Rate", "Taxable", "Tax", "Total"]
    data = [header]
    for i, ln in enumerate(lines, start=1):
        data.append(
            [
                str(i),
                (
                    (
                        f"{ln['vendor_name']} · {ln['sku']}"
                        if (ln.get("vendor_name") or "").strip()
                        else ln["sku"]
                    )
                    + f"\n{ln['description']}"
                )[:110],
                ln.get("hsn_sac") or "—",
                _money(ln["quantity"]),
                _money(ln["unit_price"]),
                _money(ln["line_taxable"]),
                _money(ln["line_tax"]),
                _money(ln["line_total"]),
            ]
        )

    table = Table(data, colWidths=[16, 175, 42, 38, 52, 52, 48, 52])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2744")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c5d0dc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fb")]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))

    totals_rows = [
        ["Subtotal", _money(subtotal)],
        ["Discount", _money(discount_amount)],
        ["Taxable value", _money(taxable_amount)],
        ["CGST", _money(cgst_amount)],
        ["SGST", _money(sgst_amount)],
        ["IGST", _money(igst_amount)],
        ["Grand Total", f"{currency} {_money(total_amount)}"],
    ]
    if amount_paid is not None:
        paid = float(amount_paid or 0)
        bal = float(total_amount) - paid
        totals_rows.append(["Amount paid", _money(paid)])
        totals_rows.append(["Balance due", f"{currency} {_money(bal)}"])

    totals = Table(totals_rows, colWidths=[110, 100], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 5), (-1, 6), "Helvetica-Bold"),
                ("LINEABOVE", (0, 6), (-1, 6), 1, colors.HexColor("#0f2744")),
            ]
        )
    )
    story.append(totals)

    bank_name = getattr(company, "bank_name", None) if company else None
    if bank_name or (company and getattr(company, "upi_id", None)):
        story.append(Spacer(1, 8))
        bank_bits = [
            f"<b>Bank details</b>",
            f"{bank_name or ''}"
            + (f" · A/c {company.bank_account}" if getattr(company, "bank_account", None) else ""),
            (f"IFSC {company.bank_ifsc}" if getattr(company, "bank_ifsc", None) else ""),
            (f"Branch {company.bank_branch}" if getattr(company, "bank_branch", None) else ""),
            (f"UPI {company.upi_id}" if getattr(company, "upi_id", None) else ""),
        ]
        story.append(Paragraph("<br/>".join([b for b in bank_bits if b]), small))

    if notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>Notes</b><br/>{notes}", small))

    if terms:
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "<b>Terms &amp; conditions</b><br/>" + terms.replace("\n", "<br/>"),
                small,
            )
        )

    footer = getattr(company, "invoice_footer", None) if company else None
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            footer
            or "Computer-generated tax document from Kevantic Quote & Billing.",
            small,
        )
    )

    doc.build(story)
    return buf.getvalue()
