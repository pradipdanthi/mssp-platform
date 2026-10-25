"""Tally-style India GST tax engine for quotes and invoices."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TWOPLACES = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class LineTaxResult:
    line_subtotal: Decimal
    line_taxable: Decimal
    line_tax: Decimal
    line_total: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal


@dataclass
class DocTaxResult:
    tax_mode: str
    subtotal: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    lines: list[LineTaxResult]


def resolve_tax_mode(
    *,
    company_state_code: str,
    party_state_code: str,
    is_export: bool,
    lut_filed: bool,
    forced: str | None = None,
) -> str:
    if forced and forced != "auto":
        return forced
    if is_export:
        return "export_zero" if lut_filed else "export_with_igst"
    if (company_state_code or "").strip() == (party_state_code or "").strip():
        return "cgst_sgst"
    return "igst"


def calc_line(
    *,
    quantity: Decimal,
    unit_price: Decimal,
    discount_percent: Decimal,
    gst_rate: Decimal,
    tax_mode: str,
) -> LineTaxResult:
    qty = money(quantity)
    price = money(unit_price)
    disc = money(discount_percent)
    rate = money(gst_rate)

    subtotal = money(qty * price)
    line_disc = money(subtotal * disc / Decimal("100"))
    taxable = money(subtotal - line_disc)

    if tax_mode == "export_zero":
        tax = money(0)
        cgst = sgst = igst = money(0)
    elif tax_mode == "cgst_sgst":
        half = money(rate / Decimal("2"))
        cgst = money(taxable * half / Decimal("100"))
        sgst = money(taxable * half / Decimal("100"))
        igst = money(0)
        tax = money(cgst + sgst)
    else:
        # igst or export_with_igst
        igst = money(taxable * rate / Decimal("100"))
        cgst = sgst = money(0)
        tax = igst

    return LineTaxResult(
        line_subtotal=subtotal,
        line_taxable=taxable,
        line_tax=tax,
        line_total=money(taxable + tax),
        cgst=cgst,
        sgst=sgst,
        igst=igst,
    )


def calc_document(
    lines: list[dict],
    *,
    doc_discount_percent: Decimal = Decimal("0"),
    tax_mode: str,
) -> DocTaxResult:
    """lines: dicts with quantity, unit_price, discount_percent, gst_rate."""
    line_results: list[LineTaxResult] = []
    for raw in lines:
        line_results.append(
            calc_line(
                quantity=Decimal(str(raw["quantity"])),
                unit_price=Decimal(str(raw["unit_price"])),
                discount_percent=Decimal(str(raw.get("discount_percent") or 0)),
                gst_rate=Decimal(str(raw.get("gst_rate") or 18)),
                tax_mode=tax_mode,
            )
        )

    subtotal = money(sum((r.line_subtotal for r in line_results), Decimal("0")))
    # document-level discount applies on sum of line taxables before GST
    pre_tax = money(sum((r.line_taxable for r in line_results), Decimal("0")))
    doc_disc = money(pre_tax * money(doc_discount_percent) / Decimal("100"))

    # redistribute doc discount proportionally and recompute tax
    if doc_disc > 0 and pre_tax > 0:
        adjusted: list[LineTaxResult] = []
        remaining_disc = doc_disc
        for i, (raw, r) in enumerate(zip(lines, line_results)):
            if i == len(lines) - 1:
                share = remaining_disc
            else:
                share = money(doc_disc * (r.line_taxable / pre_tax))
                remaining_disc = money(remaining_disc - share)
            new_taxable = money(r.line_taxable - share)
            # rebuild tax from adjusted taxable
            rate = money(raw.get("gst_rate") or 18)
            if tax_mode == "export_zero":
                tax = cgst = sgst = igst = money(0)
            elif tax_mode == "cgst_sgst":
                half = money(rate / Decimal("2"))
                cgst = money(new_taxable * half / Decimal("100"))
                sgst = money(new_taxable * half / Decimal("100"))
                igst = money(0)
                tax = money(cgst + sgst)
            else:
                igst = money(new_taxable * rate / Decimal("100"))
                cgst = sgst = money(0)
                tax = igst
            adjusted.append(
                LineTaxResult(
                    line_subtotal=r.line_subtotal,
                    line_taxable=new_taxable,
                    line_tax=tax,
                    line_total=money(new_taxable + tax),
                    cgst=cgst,
                    sgst=sgst,
                    igst=igst,
                )
            )
        line_results = adjusted

    taxable = money(sum((r.line_taxable for r in line_results), Decimal("0")))
    cgst_amount = money(sum((r.cgst for r in line_results), Decimal("0")))
    sgst_amount = money(sum((r.sgst for r in line_results), Decimal("0")))
    igst_amount = money(sum((r.igst for r in line_results), Decimal("0")))
    total = money(taxable + cgst_amount + sgst_amount + igst_amount)
    discount_amount = money(subtotal - taxable)

    return DocTaxResult(
        tax_mode=tax_mode,
        subtotal=subtotal,
        discount_amount=discount_amount,
        taxable_amount=taxable,
        cgst_amount=cgst_amount,
        sgst_amount=sgst_amount,
        igst_amount=igst_amount,
        total_amount=total,
        lines=line_results,
    )
