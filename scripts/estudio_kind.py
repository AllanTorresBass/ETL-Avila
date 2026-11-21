"""Classify one service line or page as consulta, estudio, or cargo.

The study itself comes from ``especialidad_normalize``. This module only
decides the kind: a diagnostic procedure is an estudio, a visit line is a
consulta, and a facility stop-word is a cargo. Consult notes that merely
request a test are not estudios.
"""

from __future__ import annotations

import re

from especialidad_normalize import default_catalog, normalize_text
from invoice_rules import fold

DIAGNOSTIC_MODALITIES = {"imagen", "laboratorio", "endoscopia", "funcional"}
SKIP_PROCEDURES = {"terapia_respiratoria", "quimioterapia", "radioterapia"}

# Short tokens that are real study names on a title or an order, not in prose.
TITLE_SHORT = {"RX", "TAC", "TC", "TSH", "PCR", "PSA", "EKG", "ECG", "ECO", "GGT"}

CARGO_TERMS = {
    "TACHADURAS",
    "QUIROFANO",
    "FARMACOS",
    "RESTAURACION",
    "EXODONCIA",
    "SEDACION",
    "MATERIAL MEDICO",
    "USO DE EMERGENCIA",
    "CONCENTRADO GLOBULAR",
    "SERVICIOS HOSPITALARIOS",
}

FAMILY_OF = {
    "examenes_laboratorio": "laboratorio",
    "serologia": "laboratorio",
    "antibiograma": "laboratorio",
    "citologia": "anatomia_patologica",
    "biopsia": "anatomia_patologica",
    "rayos_x": "rayos_x",
    "fistulografia": "rayos_x",
    "ecografia": "ecografia",
    "ecomamografia": "ecografia",
    "mamografia": "mamografia",
    "tomografia": "tomografia",
    "angiotomografia": "tomografia",
    "resonancia": "resonancia",
    "densitometria": "densitometria",
    "gammagrama": "medicina_nuclear",
    "fluororetinografia": "oftalmologia",
    "campo_visual": "oftalmologia",
    "ecocardiograma": "corazon",
    "electrocardiograma": "corazon",
    "holter": "corazon",
    "prueba_esfuerzo": "corazon",
    "coronariografia": "corazon",
    "mapa": "corazon",
    "endoscopia_digestiva": "endoscopia",
    "colonoscopia": "endoscopia",
    "colposcopia": "endoscopia",
    "cistoscopia": "endoscopia",
    "laringoscopia": "endoscopia",
    "audiometria": "funcional",
    "electromiografia": "funcional",
    "electroencefalograma": "funcional",
    "espirometria": "funcional",
    "flujometria": "funcional",
}

_CONSULT_LINE = re.compile(r"\bCONSULTA\b|\bVALORACION\b")
_CONSULT_NOTE = re.compile(r"MOTIVO\s+(?:DE\s+)?CONSULTA|SE REALIZ\w{0,4}.{0,40}CONSULTA")
_CONSULT_ORDER = re.compile(r"PARA CONSULTA|TIPO DE SERVICIO\s*:?\s*CONSULTA|ESPECIALIDAD REFERIDA")
_STUDY_CUE = re.compile(r"\bESTUDIOS?\b|\bIMAGEN(?:ES)?\b|\bLABORATORIO\b")


def family_of(code: str | None) -> str | None:
    if not code:
        return None
    return FAMILY_OF.get(code)


def diagnostic_code(matches: list, *, short: str) -> str | None:
    """``short`` is ``all`` (fiscal), ``title`` (order or result title), or ``none``."""
    catalog = default_catalog()
    for match in matches:
        code = match.procedimiento
        term = match.term.term if match.term else ""
        if not code or match.kind != "procedure":
            continue
        if code in SKIP_PROCEDURES:
            continue
        modality = (catalog.procedimientos.get(code) or {}).get("modality")
        if modality not in DIAGNOSTIC_MODALITIES:
            continue
        if len(term) <= 3 and short == "none":
            continue
        if len(term) <= 3 and short == "title" and term not in TITLE_SHORT:
            continue
        return code
    return None


def classify_line(label: str) -> tuple[str, str | None]:
    """Return ``(consulta|estudio|cargo|skip, procedimiento code)``."""
    matches = normalize_text(label, "fiscal_line")
    code = diagnostic_code(matches, short="all")
    if code:
        return "estudio", code
    folded = fold(label or "")
    if _CONSULT_LINE.search(folded):
        return "consulta", None
    if any(match.term and match.kind == "stop" and match.term.term in CARGO_TERMS for match in matches):
        return "cargo", None
    return "skip", None


def is_consult_note(text: str) -> bool:
    return bool(_CONSULT_NOTE.search(fold(text or "")))


def classify_result_page(text: str, document_type: str) -> tuple[str, str | None] | None:
    """An estudio from a result sheet, or None when the page is a consult."""
    if document_type in {"laboratorio", "imagenologia"}:
        head = "\n".join(fold(text or "").splitlines()[:20])
        code = diagnostic_code(normalize_text(head, "report_title"), short="title")
        if not code and document_type == "laboratorio":
            code = "examenes_laboratorio"
        return "estudio", code
    if document_type not in {"informe_medico", "otro_anexo"}:
        return None
    if is_consult_note(text or ""):
        return None
    head = "\n".join(fold(text or "").splitlines()[:20])
    code = diagnostic_code(normalize_text(head, "report_title"), short="title")
    if not code:
        return None
    return "estudio", code


def classify_order(text: str) -> tuple[str, str | None, str] | None:
    """Return ``(estudio, code or None, matched|unmatched)`` or None for a consult order."""
    head = "\n".join(fold(text or "").splitlines()[:40])
    code = diagnostic_code(normalize_text(head, "report_title"), short="title")
    if code:
        return "estudio", code, "matched"
    consult_order = _CONSULT_ORDER.search(head)
    if _STUDY_CUE.search(head) and not consult_order:
        return "estudio", None, "unmatched"
    return None
