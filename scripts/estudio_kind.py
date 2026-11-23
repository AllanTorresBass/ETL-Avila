"""Classify one service line or page as consulta, estudio, or cargo.

The study itself comes from ``especialidad_normalize``. This module only
decides the kind: a diagnostic procedure is an estudio, a visit line is a
consulta, and a facility stop-word is a cargo. Consult notes that merely
request a test are not estudios.
"""

from __future__ import annotations

import re

from especialidad_normalize import clean_tokens, default_catalog, normalize_text
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


# Modality words. A site or a longer test name is more specific than these.
GENERIC_TERMS = {
    "LABORATORIO",
    "LABORATORIOS",
    "PERFIL",
    "RX",
    "ECO",
    "TAC",
    "TC",
    "RAYOS X",
    "RADIOGRAFIA",
    "ECOGRAFIA",
    "ULTRASONIDO",
    "ECOSONOGRAMA",
    "ECOGRAMA",
    "TOMOGRAFIA",
    "RESONANCIA",
    "RESONANCIA MAGNETICA",
    "ENDOSCOPIA",
    "IMAGEN",
    "IMAGENOLOGIA",
    "DOPPLER",
}

PANEL_TERMS = {"HEMATOLOGIA COMPLETA"}

_EXPAND = {
    "RXTORAX": "Rayos X de tórax",
    "TCTORAX": "Tomografía de tórax",
    "UROTAC": "Tomografía urológica",
    "NT PROBNP": "NT-proBNP",
    "NT PROB": "NT-proBNP",
}

_ACCENT = {
    "ACIDO": "ÁCIDO",
    "URICO": "ÚRICO",
    "PELVICA": "PÉLVICA",
    "PELVICO": "PÉLVICO",
    "OBSTETRICA": "OBSTÉTRICA",
    "PROSTATICA": "PROSTÁTICA",
    "HEPATICA": "HEPÁTICA",
    "TIROIDEA": "TIROIDEA",
    "TIROIDEO": "TIROIDEO",
    "CAROTIDEA": "CAROTÍDEA",
    "CAROTIDEO": "CAROTÍDEO",
    "CRANEO": "CRÁNEO",
    "TORAX": "TÓRAX",
}

_UPPER = {"NT", "PROBNP", "TSH", "PCR", "PSA", "GGT", "VDRL", "ANA", "RX", "TAC", "TC", "EKG", "ECG", "MAPA", "HDL", "LDL"}

# Closed list. Anything else on the page (a name, a clinic) is not copied.
_NOUN_SITES = {
    "TORAX": "de tórax",
    "ABDOMEN": "de abdomen",
    "CRANEO": "de cráneo",
    "RODILLA": "de rodilla",
    "HOMBRO": "de hombro",
    "TOBILLO": "de tobillo",
    "CADERA": "de cadera",
    "TIROIDES": "de tiroides",
    "MAMA": "de mama",
    "COLUMNA": "de columna",
    "MANO": "de mano",
    "PIE": "de pie",
}
_ADJ_SITES = {
    "ABDOMINAL": "abdominal",
    "PELVICA": "pélvica",
    "PELVICO": "pélvico",
    "RENAL": "renal",
    "CEREBRAL": "cerebral",
    "CERVICAL": "cervical",
    "LUMBAR": "lumbar",
    "DORSAL": "dorsal",
    "TRANSVAGINAL": "transvaginal",
    "TRANSRECTAL": "transrectal",
    "OBSTETRICA": "obstétrica",
    "CONTRASTADA": "contrastada",
    "CONTRASTADO": "contrastado",
    "SIMPLE": "simple",
    "COMPLETA": "completa",
    "COMPLETO": "completo",
    "PROSTATICA": "prostática",
    "HEPATICA": "hepática",
    "VESICULAR": "vesicular",
    "TESTICULAR": "testicular",
    "MAMARIA": "mamaria",
    "MAMARIO": "mamario",
    "CAROTIDEA": "carotídea",
    "CAROTIDEO": "carotídeo",
    "TIROIDEA": "tiroidea",
    "TIROIDEO": "tiroideo",
    "URINARIA": "urinaria",
    "VENOSO": "venoso",
    "VENOSA": "venosa",
    "ARTERIAL": "arterial",
}


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


def _pretty_word(word: str, *, first: bool) -> str:
    if word in _UPPER or (len(word) <= 3 and word.isalpha()):
        return word
    stem = word
    if stem.endswith("GRAFIA"):
        stem = stem[:-6] + "GRAFÍA"
    elif stem.endswith("LOGIA"):
        stem = stem[:-5] + "LOGÍA"
    stem = _ACCENT.get(stem, stem)
    if first:
        return stem[:1] + stem[1:].lower()
    return stem.lower()


def _pretty(term: str) -> str:
    return _EXPAND.get(term) or " ".join(_pretty_word(word, first=i == 0) for i, word in enumerate(term.split()))


def _procedure_name(code: str | None) -> str | None:
    if not code:
        return None
    return (default_catalog().procedimientos.get(code) or {}).get("name_es")


def _line_containing(text: str, term: str) -> str:
    folded = fold(text or "")
    for line in folded.splitlines():
        if term in line:
            return line
    return folded


_SITE_OVERLAP = (
    ("de tiroides", "tiroidea"),
    ("de tiroides", "tiroideo"),
    ("de mama", "mamaria"),
    ("de mama", "mamario"),
    ("de cráneo", "cerebral"),
)


def _site_labels(line: str, used: set[str], *, qualifiers: bool) -> list[str]:
    labels: list[str] = []
    for token in clean_tokens(line)[0]:
        if token in used or token in GENERIC_TERMS:
            continue
        if token in {"COMPLETA", "COMPLETO"} and not qualifiers:
            continue
        label = _NOUN_SITES.get(token) or _ADJ_SITES.get(token)
        if label and label not in labels:
            labels.append(label)
    for noun, adjective in _SITE_OVERLAP:
        if noun in labels and adjective in labels:
            labels.remove(adjective)
    return labels


_FEMININE_SITE = {
    "pélvico": "pélvica",
    "mamario": "mamaria",
    "tiroideo": "tiroidea",
    "venoso": "venosa",
    "contrastado": "contrastada",
    "completo": "completa",
    "prostático": "prostática",
    "carotídeo": "carotídea",
}


def _with_sites(base: str, sites: list[str]) -> str:
    if not sites:
        return base
    head = base.split(" · ")[0]
    if head.endswith(("grafía", "scopia", "logía", "metría")):
        sites = [_FEMININE_SITE.get(site, site) for site in sites]
    return f"{base} {' '.join(sites)}"


def specific_name(text: str, code: str | None, *, context: str = "report_title") -> str | None:
    """The most specific study name the line or the page title supports.

    A catalog test (Hemograma, Uretrocistografía) wins. A modality plus a
    body site (Rayos X de tórax) is next. The procedure name is the fallback
    when the page only says Laboratorio or lists many analytes.
    Words outside the catalog and the site list are ignored.
    """
    catalog = default_catalog()
    matches = normalize_text(text or "", context)
    scoped = []
    for match in matches:
        if match.kind != "procedure" or not match.term or not match.procedimiento:
            continue
        if match.procedimiento in SKIP_PROCEDURES:
            continue
        modality = (catalog.procedimientos.get(match.procedimiento) or {}).get("modality")
        if modality not in DIAGNOSTIC_MODALITIES:
            continue
        if code and match.procedimiento != code:
            continue
        scoped.append(match)
    if not scoped:
        return _procedure_name(code)

    specifics: list[str] = []
    for match in scoped:
        term = match.term.term
        if term in GENERIC_TERMS or term in specifics:
            continue
        specifics.append(term)

    panel = next((term for term in specifics if term in PANEL_TERMS), None)
    if panel:
        return _pretty(panel)
    if len(specifics) == 1:
        term = specifics[0]
        if term in _EXPAND:
            return _EXPAND[term]
        sites = _sites_for(text or "", term, code, context, qualifiers=True, used=set(term.split()))
        return _with_sites(_pretty(term), sites)
    if context == "fiscal_line" and 1 < len(specifics) <= 3:
        return " · ".join(_pretty(term) for term in specifics)
    if specifics:
        return _procedure_name(code)
    term = scoped[0].term.term
    sites = _sites_for(text or "", term, code, context, qualifiers=False, used=set())
    base = "Perfil" if term == "PERFIL" else (_procedure_name(code) or "")
    if sites and base:
        return _with_sites(base, sites)
    return _procedure_name(code)


def _sites_for(text: str, term: str, code: str | None, context: str, *, qualifiers: bool, used: set[str]) -> list[str]:
    line = _line_containing(text, term)
    if code and _other_procedure(line, code, context):
        return []
    return _site_labels(line, used, qualifiers=qualifiers)


def _other_procedure(text: str, code: str, context: str) -> bool:
    catalog = default_catalog()
    for match in normalize_text(text, context):
        if match.kind != "procedure" or not match.procedimiento or match.procedimiento == code:
            continue
        if match.procedimiento in SKIP_PROCEDURES:
            continue
        modality = (catalog.procedimientos.get(match.procedimiento) or {}).get("modality")
        if modality in DIAGNOSTIC_MODALITIES:
            return True
    return False
