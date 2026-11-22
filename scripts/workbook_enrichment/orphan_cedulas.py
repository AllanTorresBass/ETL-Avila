"""Decide whether an orphan cédula may fill an empty factura role.

The packet keeps any titular or beneficiario it already has. This function
never replaces a person and never returns a link for someone invoice truth
already removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from invoice_rules import fold
from workbook_enrichment.upsert_persons import row_is_titular_self

# A factura already has a titular, but not a single comparable cédula.
OCCUPIED = "\x00"


@dataclass(frozen=True)
class OrphanDecision:
    action: str
    ci: str
    reason: str
    role: str


def ci_key(value: Any) -> str | None:
    """Digits only, without leading zeros. ``OCCUPIED`` stays as the sentinel."""
    if value == OCCUPIED:
        return OCCUPIED
    digits = re.sub(r"\D", "", "" if value is None else str(value))
    if not digits:
        return None
    return digits.lstrip("0") or digits


def decide_orphan_row(
    row: dict[str, Any],
    *,
    invoice_found: bool,
    titular_ci: str | None,
    beneficiario_cis: set[str] | None = None,
    eligible_cis: set[str],
    truth_removed_cis: set[str] | None = None,
    open_conflict_cis: set[str] | None = None,
) -> list[OrphanDecision]:
    """One decision per cédula on the row that this pass is allowed to see."""
    removed = truth_removed_cis or set()
    conflicts = open_conflict_cis or set()
    current_titular = ci_key(titular_ci)
    current_beneficiarios = {key for key in (ci_key(ci) for ci in (beneficiario_cis or set())) if key}
    titular = ci_key(row.get("titular_ci"))
    beneficiario = ci_key(row.get("beneficiario_ci"))
    self_row = row_is_titular_self(row)
    roles: list[tuple[str, str]] = []
    if titular:
        roles.append(("titular", titular))
    if beneficiario and not (self_row and beneficiario == titular):
        roles.append(("beneficiario", beneficiario))

    effective_titular = None if current_titular == OCCUPIED else current_titular
    decisions: list[OrphanDecision] = []
    for role, ci in roles:
        decision = _decide_one(
            role,
            ci,
            invoice_number=row.get("invoice_number"),
            invoice_found=invoice_found,
            current_titular=current_titular,
            effective_titular=effective_titular,
            current_beneficiarios=current_beneficiarios,
            eligible_cis=eligible_cis,
            removed=removed,
            conflicts=conflicts,
        )
        if decision is None:
            continue
        decisions.append(decision)
        if decision.action == "link_titular":
            effective_titular = ci
    return decisions


def _decide_one(
    role: str,
    ci: str,
    *,
    invoice_number: str | None,
    invoice_found: bool,
    current_titular: str | None,
    effective_titular: str | None,
    current_beneficiarios: set[str],
    eligible_cis: set[str],
    removed: set[str],
    conflicts: set[str],
) -> OrphanDecision | None:
    if ci in removed:
        return OrphanDecision("skip", ci, "truth_blocked", role)
    if ci in conflicts:
        return OrphanDecision("skip", ci, "open_ci_conflict", role)
    if ci not in eligible_cis:
        return None
    if not invoice_number:
        return OrphanDecision("skip", ci, "no_factura_number", role)
    if not invoice_found:
        return OrphanDecision("skip", ci, "factura_not_loaded", role)
    if role == "titular":
        return _titular_slot(ci, current_titular, current_beneficiarios)
    return _beneficiario_slot(ci, current_titular, effective_titular, current_beneficiarios)


def _titular_slot(
    ci: str,
    current_titular: str | None,
    current_beneficiarios: set[str],
) -> OrphanDecision:
    if ci in current_beneficiarios:
        return OrphanDecision("skip", ci, "already_linked", "titular")
    if current_titular == OCCUPIED or (current_titular and current_titular != ci):
        return OrphanDecision("review", ci, "packet_conflict", "titular")
    if current_titular == ci:
        return OrphanDecision("skip", ci, "already_linked", "titular")
    return OrphanDecision("link_titular", ci, "titular_slot_empty", "titular")


def _beneficiario_slot(
    ci: str,
    current_titular: str | None,
    effective_titular: str | None,
    current_beneficiarios: set[str],
) -> OrphanDecision:
    if current_titular == OCCUPIED:
        return OrphanDecision("review", ci, "packet_conflict", "beneficiario")
    if ci in current_beneficiarios or ci == effective_titular:
        return OrphanDecision("skip", ci, "already_linked", "beneficiario")
    if effective_titular is None:
        return OrphanDecision("skip", ci, "beneficiario_needs_titular", "beneficiario")
    if current_beneficiarios:
        return OrphanDecision("review", ci, "packet_conflict", "beneficiario")
    return OrphanDecision("link_beneficiario", ci, "beneficiario_slot_empty", "beneficiario")


LINK_BENEFICIARIO = "link_beneficiario"
PROMOTE_TITULAR = "promote_titular"
REVIEW_DUPLICATE = "review_duplicate"
LEAVE = "leave"


def cedula_digits(value: Any) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def one_digit_apart(left: Any, right: Any) -> bool:
    """True when two cédulas of at least 7 digits differ in exactly one place."""
    first, second = cedula_digits(left), cedula_digits(right)
    if len(first) < 7 or len(first) != len(second) or first == second:
        return False
    return sum(a != b for a, b in zip(first, second)) == 1


def name_tokens(name: str | None) -> set[str]:
    folded = fold(name or "")
    return {token for token in re.split(r"[^A-Z]+", folded) if len(token) > 2}


def shares_name_token(left: str | None, right: str | None) -> bool:
    return bool(name_tokens(left) & name_tokens(right))


def is_factura_span(number: str | None) -> bool:
    """A range bundle is not one factura. ``range:18030-18134`` and ``18030-18134``."""
    text = "" if number is None else str(number).strip()
    return text.startswith("range:") or "-" in text


def decide_never_linked(
    ci: Any,
    *,
    fiscal_titular_ci: Any = None,
    fiscal_patient_ci: Any = None,
    invoice_number: str | None = None,
    titular_slot_empty: bool = False,
    twin_shares_name: bool = False,
) -> str:
    """Choose one action for a cédula that has no factura, authorization, or document.

    A one-digit twin that shares a name is a review and stops the page. A span is
    never a link target. The caller still has to read the printed page before
    creating an invoice, and must not replace a beneficiario who is already there.
    """
    digits = cedula_digits(ci)
    if len(digits) <= 6:
        return LEAVE
    if twin_shares_name:
        return REVIEW_DUPLICATE
    if is_factura_span(invoice_number) or not cedula_digits(invoice_number):
        return LEAVE
    titular = cedula_digits(fiscal_titular_ci)
    patient = cedula_digits(fiscal_patient_ci)
    if patient == digits and titular and titular != digits:
        return LINK_BENEFICIARIO
    if titular == digits and titular_slot_empty:
        return PROMOTE_TITULAR
    return LEAVE
