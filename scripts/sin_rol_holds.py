"""Decide whether a held C.1 patient can take the beneficiario slot.

The factura on the page has to be the stored factura. A range bucket is that
factura only when it is ``range:`` plus the single number on the page. The
titular cédula on the page has to be the titular already stored. An empty slot
is linked. A slot with no cédula is replaced when that row is the same name or
when this patient was already on the factura and later cleared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from person_upsert import fold_person_name

_NUMBER = re.compile(r"\d{3,9}")


@dataclass(frozen=True)
class HoldDecision:
    action: str
    reason: str


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _same_name(a: str | None, b: str | None) -> bool:
    fa = set(fold_person_name(a or "").split())
    fb = set(fold_person_name(b or "").split())
    if len(fa) < 2 or len(fb) < 2:
        return False
    shorter, longer = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    return shorter <= longer


def page_owns_invoice(stored: str | None, ocr_number: str | None) -> bool:
    """True when the stored key is this page's factura, not a multi-factura range."""
    number = _digits(ocr_number)
    if not stored or not _NUMBER.fullmatch(number):
        return False
    return stored == number or stored == f"range:{number}"


def decide_hold(
    *,
    page_patient_ci: str | None,
    page_titular_ci: str | None,
    patient_ci: str,
    patient_name: str | None,
    stored_invoice: str | None,
    ocr_invoice: str | None,
    titular_ci: str | None,
    titular_count: int,
    beneficiaries: list[dict],
    patient_was_cleared: bool,
    already_on_invoice: bool,
) -> HoldDecision:
    patient = _digits(patient_ci)
    page_patient = _digits(page_patient_ci)
    page_titular = _digits(page_titular_ci)
    stored_titular = _digits(titular_ci)
    if not patient or page_patient != patient:
        return HoldDecision("skip", "page_patient_mismatch")
    if not page_titular or page_titular == patient:
        return HoldDecision("skip", "page_not_a_pair")
    if not page_owns_invoice(stored_invoice, ocr_invoice):
        return HoldDecision("skip", "factura_not_this_page")
    if already_on_invoice:
        return HoldDecision("skip", "already_on_invoice")
    if titular_count != 1 or stored_titular != page_titular:
        return HoldDecision("skip", "titular_mismatch")
    if not beneficiaries:
        return HoldDecision("link", "empty_slot")
    if len(beneficiaries) != 1:
        return HoldDecision("skip", "many_beneficiarios")
    ben = beneficiaries[0]
    if _digits(ben.get("ci")):
        return HoldDecision("skip", "slot_has_ci")
    if ben.get("source") == "workbook":
        return HoldDecision("skip", "workbook_beneficiario")
    if _same_name(ben.get("name"), patient_name):
        return HoldDecision("replace", "same_name_no_ci")
    if patient_was_cleared:
        return HoldDecision("replace", "cleared_patient")
    return HoldDecision("skip", "nameless_other")
