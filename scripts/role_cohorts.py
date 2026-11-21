"""Per-invoice titular/beneficiario verification cohorts.

Every loaded invoice gets exactly one primary cohort (priority order below).
Counts and suggested actions are PHI-free; the verify queue may carry FACT
numbers and evidence flags under ``output/persons/_queue/`` (git-ignored).
"""

from __future__ import annotations

from typing import Any

from titular_queue import is_junk_titular
from upload_documents_to_blob import _names_refer_to_same_person

# Priority order — first match wins.
COHORTS: tuple[str, ...] = (
    "multi_titular",
    "blocked_review",
    "no_titular",
    "id_docs_no_ci",
    "mismatch_no_beneficiario",
    "nameless_titular",
    "self_visit_ok",
    "resolved_pair",
    "unknown_links",
    "weak_evidence",
)

BLOCKING_REVIEW_KINDS = frozenset(
    {"ci_conflict", "workbook_titular", "multiple_ci", "acta_titular"}
)

IDENTITY_DOC_TYPES = (
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
)

# Closed vocabulary of suggested next actions (no free text).
ACTIONS: dict[str, str] = {
    "multi_titular": "promote_ci",
    "blocked_review": "open_or_resolve_review",
    "no_titular": "promote_ci",
    "id_docs_no_ci": "strengthen_ci_ocr",
    "mismatch_no_beneficiario": "link_path_beneficiario",
    "nameless_titular": "fill_titular_name",
    "self_visit_ok": "noop_self_visit",
    "resolved_pair": "noop_self_visit",
    "unknown_links": "merge_duplicate",
    "weak_evidence": "reclassify_identity",
}

# When fiscal patient differs, prefer fiscal link over path.
MISMATCH_FISCAL_ACTION = "link_fiscal_beneficiario"


def patient_differs_from_titular(
    *,
    titular_name: str | None,
    titular_ci: str | None,
    patient_name: str | None,
    patient_ci: str | None,
) -> bool:
    """True when a patient signal names a different person than the titular."""
    if not patient_name and not patient_ci:
        return False
    if patient_ci and titular_ci and patient_ci == titular_ci:
        return False
    if patient_name and titular_name and _names_refer_to_same_person(patient_name, titular_name):
        return False
    # Path CI alone with no name, different from titular CI → different person.
    if patient_ci and titular_ci and patient_ci != titular_ci:
        return True
    if patient_name and not titular_name:
        # Nameless titular — cannot safely claim mismatch (same person risk).
        return False
    if patient_name and titular_name:
        return not _names_refer_to_same_person(patient_name, titular_name)
    return False


def assign_cohort(signals: dict[str, Any]) -> tuple[str, str]:
    """Return ``(cohort, suggested_action)`` for one invoice's evidence bag."""
    titular_n = int(signals.get("titular_count") or 0)
    beneficiario_n = int(signals.get("beneficiario_count") or 0)
    unknown_n = int(signals.get("unknown_count") or 0)
    open_reviews = list(signals.get("open_reviews") or [])
    has_id_docs = bool(signals.get("has_id_docs"))
    titular_ci = (signals.get("titular_ci") or "").strip() or None
    titular_name = (signals.get("titular_name") or "").strip() or None
    titular_source = (signals.get("titular_source") or "").strip() or None
    path_name = (signals.get("path_name") or "").strip() or None
    path_ci = (signals.get("path_ci") or "").strip() or None
    fiscal_patient_name = (signals.get("fiscal_patient_name") or "").strip() or None
    fiscal_patient_ci = (signals.get("fiscal_patient_ci") or "").strip() or None

    if titular_n > 1:
        return "multi_titular", ACTIONS["multi_titular"]

    if any(k in BLOCKING_REVIEW_KINDS for k in open_reviews):
        return "blocked_review", ACTIONS["blocked_review"]

    if titular_n == 0:
        return "no_titular", ACTIONS["no_titular"]

    if has_id_docs and not titular_ci:
        return "id_docs_no_ci", ACTIONS["id_docs_no_ci"]

    path_mismatch = patient_differs_from_titular(
        titular_name=titular_name,
        titular_ci=titular_ci,
        patient_name=path_name,
        patient_ci=path_ci,
    )
    fiscal_mismatch = patient_differs_from_titular(
        titular_name=titular_name,
        titular_ci=titular_ci,
        patient_name=fiscal_patient_name,
        patient_ci=fiscal_patient_ci,
    )
    if beneficiario_n == 0 and (path_mismatch or fiscal_mismatch):
        action = MISMATCH_FISCAL_ACTION if fiscal_mismatch else ACTIONS["mismatch_no_beneficiario"]
        return "mismatch_no_beneficiario", action

    nameless = is_junk_titular(
        {"full_name": titular_name or "", "identity_number": titular_ci or ""}
    )
    if titular_ci and nameless:
        return "nameless_titular", ACTIONS["nameless_titular"]

    if beneficiario_n >= 1:
        return "resolved_pair", ACTIONS["resolved_pair"]

    # Titular-only from here.
    if unknown_n > 0:
        return "unknown_links", ACTIONS["unknown_links"]

    if titular_source in (None, "", "legacy_unknown", "path") and not has_id_docs:
        return "weak_evidence", ACTIONS["weak_evidence"]

    return "self_visit_ok", ACTIONS["self_visit_ok"]


def empty_cohort_counts() -> dict[str, int]:
    return {c: 0 for c in COHORTS}
