"""Map OCR / path evidence to personal document_type codes for Neon + Blob."""

from __future__ import annotations

import re
from pathlib import Path

from invoice_pages import judge_page
from invoice_rules import MONTHS, fold

DOCUMENT_TYPES = (
    "factura_fiscal",
    "cedula_identidad",
    "pasaporte",
    "carnet",
    "documentos_identificacion",
    "acta_nacimiento",
    "egreso",
    "ingreso",
    "informe_medico",
    "comprobante",
    "carta_aval",
    "presupuesto",
    "laboratorio",
    "imagenologia",
    "orden_servicio",
    "otro_anexo",
    "ilegible",
)

DOCUMENT_TYPE_LABELS_ES = {
    "factura_fiscal": "Factura fiscal",
    "cedula_identidad": "Cédula de identidad",
    "pasaporte": "Pasaporte",
    "carnet": "Carnet",
    "documentos_identificacion": "Documentos de identificación",
    "acta_nacimiento": "Acta de nacimiento",
    "egreso": "Egreso",
    "ingreso": "Ingreso",
    "informe_medico": "Informe médico",
    "comprobante": "Comprobante",
    "carta_aval": "Carta aval",
    "presupuesto": "Presupuesto",
    "laboratorio": "Laboratorio",
    "imagenologia": "Imagenología",
    "orden_servicio": "Orden de servicio",
    "otro_anexo": "Otro anexo",
    "ilegible": "Ilegible",
}

# Real plastic cédula card — not claim forms or civil-registry actas.
_CEDULA_TITLE = re.compile(r"CEDULA\s+DE\s+IDENTIDAD")
_CEDULA_CNE = re.compile(r"CONSEJO\s+NACIONAL\s+ELECTORAL")
_CEDULA_CARD_FIELDS = re.compile(
    r"APELLIDOS?\b.+\bNOMBRES?\b|\bF\.?\s*EXPEDIC|\bESTADO\s+CIVIL\b|\bVENEZOLAN[OA]\b"
)
_FORM_NOT_CEDULA = re.compile(
    r"DECLARACION\s+DE\s+SINIESTRO|\bPLANILLA\b|\bINFORME\s*:|\bDATOS\s+DEL\s+TITULAR\b|"
    r"\bDATOS\s+DE\s+LA\s+POLIZA\b|\bBENEFICIARIO\b.+\bTITULAR\b|"
    r"CEDULA\s+DE\s+IDENTIDAD\s*/\s*RIF|APELLIDOS\s+Y\s+NOMBRES\s+DEL\b|"
    r"SOLICITUD\s+(?:DE\s+)?CARTA\s+AVAL"
)
_SOLICITUD_CARTA = re.compile(r"SOLICITUD\s+(?:DE\s+)?CARTA\s+AVAL")
_CARTA_AVAL_LETTER = re.compile(r"\bCARTA\s+AVAL\b")
# Strong cues are enough on their own. A bare "registro civil" also shows up in
# clinical text, so it only counts next to an acta-specific word.
_ACTA_NACIMIENTO = re.compile(
    r"ACTA\s+(?:DE\s+)?NACIMIENTO|"
    r"UNIDAD\s+DE\s+REGISTRO\s+CIVIL|PRESENTACI[OÓ]N\s+DEL\s+NACIDO|"
    r"COMISI[OÓ]N\s+DE\s+REGISTRO\s+(?:CIVIL|ENVIL)|"
    r"\bACTA\s+N[°º\.Y]?\s*\d+"
)
_REGISTRO_CIVIL = re.compile(r"\bREGISTRO\s+CIVIL\b")
_ACTA_SUPPORT = re.compile(r"\bACTA\b|\bPRESENTANTE\b|\bFOLIO\b|\bLIBRO\b")
_CARNET_BDV = re.compile(
    r"BANCO\s+DE\s+VENEZUELA|\bBDV\b.+\bVP\b|\bCARNET\b|\bVP\s+SERVICIOS\b"
)
# Scanned cover sheets often put OCR noise between "DE" and "IDENTIFICACION".
_ID_COLLAGE = re.compile(r"DOCUMENTOS?\s+DE\s+(?:\S+\s+){0,4}?IDENTIFICACION")
_PASAPORTE_CARD = re.compile(r"\bPASAPORTE\b")
_EGRESO = re.compile(r"\bEGRESO\b|\bENGRESO\b")
_INGRESO = re.compile(r"\bINGRESO\b")
_LAB = re.compile(r"\bLABORATORIO\b|\bHEMATOLOGI")
_IMG = re.compile(r"\bRAYOS\b|\bECOGRAF|\bULTRASON|\bIMAGENOLOG")
_CARTA = re.compile(r"CARTA\s*AVAL")
_PRESUPUESTO = re.compile(r"\bPRESUPUESTO\b|\bPROFORMA\b")
_ORDEN = re.compile(r"ORDEN\s+DE\s+SERVICIO|SOLICITUD\s+DE\s+SERVICIO|\bAPS\b")
_ORDEN_TITLE = re.compile(r"ORDEN\s+DE\s+SERVICIO|SOLICITUD\s+DE\s+SERVICIO")
_PATIENT_REPORT = re.compile(
    r"INFORME\s+MEDICO|"
    r"(?:NOMBRE\s+DEL\s+PACIENTE|\bPACIENTE\s*:).{0,600}?\bDIAGNOSTICO\b|"
    r"\bDIAGNOSTICO\b.{0,600}?(?:NOMBRE\s+DEL\s+PACIENTE|\bPACIENTE\s*:)",
    re.S,
)
# Cédula digits, plain (12345678) or dotted (12.345.678). The V/E prefix must not
# be the tail of a word ("SERVICE 1234567" is not a cédula).
_CI_DIGITS = r"(\d{1,2}\.\d{3}\.\d{3}|\d{6,9})(?![\d.]*\d)"
_IDENTITY_NUMBER = re.compile(
    rf"(?<![A-Z0-9])(?:V|E)\s*-?\s*{_CI_DIGITS}"
    rf"|\bC\.?\s*I\.?\s*(?:N[°º]?\s*)?:?\s*(?:V|E)?\s*-?\s*{_CI_DIGITS}"
)
_PASSPORT_NUMBER = re.compile(r"\bP[A-Z]?\s*-?\s*([A-Z0-9]{6,12})\b")
_RIF_NUMBER = re.compile(r"\b([VEJPG])\s*-?\s*(\d{7,9})\-?(\d)?\b")
# Venezuelan cédula cards print APELLIDOS then NOMBRES (OCR order varies).
_CEDULA_APELLIDOS = re.compile(
    r"APELLIDOS?\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{1,40})",
    re.IGNORECASE,
)
_CEDULA_NOMBRES = re.compile(
    r"NOMBRES?\s*[:\-]?\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{1,40})",
    re.IGNORECASE,
)
# Path stems often look like: FACT 19263 PEDRO ROJAS or FACT 7806 ANA TORO 20.333.444
_FACT_PREFIX = re.compile(
    # Allow glued stems like "FACT 7394LUIS …" (no boundary after the digits).
    r"^(?:FACT(?:URA)?|FAC)\s*(\d{3,6})(?!\d)",
    re.IGNORECASE,
)
_PATH_CEDULA = re.compile(r"(?:V|E)?\s*-?\s*(\d{1,2}(?:[.\s]\d{3}){2}|\d{6,9})\b")
_ROLE_PREFIX = re.compile(
    r"^(?:EGRESO|ENGRESO|INGRESO|CARTA\s*AVAL|PRESUPUESTO|PROFORMA)\b[\s\-]*",
    re.IGNORECASE,
)
_TITULAR_OCR = re.compile(
    # Name stays on the TITULAR line; the next line is usually RIF / C.I. / address.
    r"TITULAR[ \t]*[:\-]?[ \t]*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ \t.'-]{2,60})",
    re.IGNORECASE,
)
_NOISE_TOKENS = {
    "PDF",
    "PPTX",
    "POTX",
    "JPG",
    "PNG",
    "IMG",
    "SCANER",
    "ESCANER",
    "PROCESADAS",
    "LISTAS",
    "DIGITALIZACIONES",
    "FACT",
    "FACTURA",
    "FACTURAS",
    "FAC",
    "SEG",
    "SEGURO",
    "SEGUROS",
    "MIRANDA",
    "PREVISORA",
    "PREVISA",
    "ALTAMIRA",
    "LATITUD",
    "LOTE",
    "PARTE",
    "CORPOELEC",
    "CATARATAS",
    "JORNADA",
    "NUEVO",
    "PRESUPUESTO",
    "PROFORMA",
    "EGRESO",
    "EGRESOS",
    "ENGRESO",
    "INGRESO",
    "CARTA",
    "AVAL",
    "ACTIVACION",
    "ACTIVACIÓN",
    "PACIENTES",
    "CONSTITUCION",
    "SENIAT",
    "VENEZOLANA",
    "VENEZOLANO",
    "VENEZOLANAS",
    "VENEZOLANOS",
    "NACIONALIDAD",
    "APELLIDOS",
    "APELLIDO",
    "NOMBRES",
    "NOMBRE",
    "CEDULA",
    "IDENTIDAD",
    "2023",
    "2024",
    "2025",
    "2026",
    "2026",
    "2027",
    *MONTHS,
}


def classify_document(
    text: str | None,
    *,
    backup_path: str = "",
    page_error: str = "",
) -> tuple[str, str]:
    """Return (document_type, evidence). Evidence is token names only."""
    if page_error and not (text or "").strip():
        return "ilegible", page_error[:80] or "unreadable"
    label, evidence = judge_page(text or "")
    if label == "unreadable":
        return "ilegible", evidence
    if label == "fiscal_invoice":
        return "factura_fiscal", evidence

    folded = fold(text or "")
    path_folded = fold(backup_path)
    stem = fold(Path(backup_path).stem) if backup_path else ""

    # Birth certificate / civil registry — often under the same GPS cover sheet
    # as ID collage pages; must win before cédula (actas quote "cédula de identidad"
    # for parents and print CNE / República / venezolano|a).
    if _ACTA_NACIMIENTO.search(folded) or (
        _REGISTRO_CIVIL.search(folded) and _ACTA_SUPPORT.search(folded)
    ):
        return "acta_nacimiento", "acta_nacimiento"

    # GPS cover sheet that mounts plastic IDs (cédula + carnet side by side).
    if _ID_COLLAGE.search(folded):
        return "documentos_identificacion", "documentos_identificacion"

    # Employee badge / carnet crop (standalone page, not the collage sheet).
    if not _SOLICITUD_CARTA.search(folded) and _CARNET_BDV.search(folded) and (
        "CARNET" in folded or "VP " in folded or "SERVICIOS" in folded
    ):
        if not _CEDULA_TITLE.search(folded):
            return "carnet", "carnet_bdv"
        # Cédula and bank carnet photographed together without the cover title.
        if not _FORM_NOT_CEDULA.search(folded):
            return "documentos_identificacion", "collage_untitled"

    # Plastic cédula card only — claim forms and actas print República / C.I.
    if not _FORM_NOT_CEDULA.search(folded) and (
        (
            _CEDULA_TITLE.search(folded)
            and (_CEDULA_CARD_FIELDS.search(folded) or _CEDULA_CNE.search(folded))
        )
        or (_CEDULA_TITLE.search(folded) and "VENEZOLAN" in folded)
    ):
        return "cedula_identidad", "cedula_card"

    # Insurer request form; its checklist mentions "Informe médico".
    if _SOLICITUD_CARTA.search(folded):
        return "carta_aval", "solicitud_carta_aval"

    # Claim forms print "C.I. o PASAPORTE" and República — settle them before
    # the passport check so they never become identity pages.
    if (
        evidence in {"comprobante", "claim_form"}
        or "COMPROBANTE" in folded
        or "LARACION DE SINIESTRO" in folded
    ):
        if "LARACION DE SINIESTRO" in folded:
            return "comprobante", "declaracion_siniestro"
        # Insurer letter "CARTA AVAL … Nro Ppto/Factura"; siniestro forms only tick a Carta Aval box.
        if evidence == "claim_form" and _CARTA_AVAL_LETTER.search(folded):
            return "carta_aval", "carta_aval_letter"
        return "comprobante", "claim_form" if evidence == "claim_form" else "comprobante"

    # Passport as a photographed page is rare. The fiscal form also prints
    # "C.I., R.I.F. o PASAPORTE" — ignore that when the page is already fiscal.
    if (
        _PASAPORTE_CARD.search(folded)
        and "FACTURA" not in folded[:200]
        and not _FORM_NOT_CEDULA.search(folded)
        and not re.search(r"C\.?\s*I\.?\s*,?\s*(?:R\.?I\.?F\.?\s*)?O\s+PASAPORTE", folded)
    ):
        if "REPUBLICA" in folded or "PASAPORTE" in folded[:400]:
            return "pasaporte", "pasaporte_card"
    # The APS footer rides on many reports; only a titled order is an orden.
    orden_title = _ORDEN_TITLE.search(folded)
    if _PATIENT_REPORT.search(folded) and not orden_title:
        return "informe_medico", "patient_report"
    if evidence == "informe" or (_ORDEN.search(folded) is None and "INFORME" in folded):
        if orden_title or (_ORDEN.search(folded) and "INFORME" not in folded):
            return "orden_servicio", "orden_servicio"
        return "informe_medico", "informe"
    if _ORDEN.search(folded):
        return "orden_servicio", "orden_servicio"

    if _EGRESO.search(folded) or _EGRESO.search(stem):
        return "egreso", "egreso"
    if _INGRESO.search(folded) or _INGRESO.search(stem):
        return "ingreso", "ingreso"
    if _LAB.search(folded):
        return "laboratorio", "laboratorio"
    if _IMG.search(folded):
        return "imagenologia", "imagenologia"
    if _CARTA.search(folded):
        return "carta_aval", "carta_aval"
    if _PRESUPUESTO.search(folded) or _PRESUPUESTO.search(stem):
        return "presupuesto", "presupuesto"
    if evidence == "clinical_terms":
        return "otro_anexo", "clinical_terms"
    # Folder name is the weakest cue: a CARTA AVAL folder also holds IDs, reports, actas.
    if _CARTA.search(path_folded):
        return "carta_aval", "carta_aval_folder"
    return "otro_anexo", evidence or "no_factura_heading"


def extract_identity_number(text: str | None) -> tuple[str, str] | None:
    """Return (identity_type, identity_number) or None. Digits only for cédula/RIF."""
    if not text:
        return None
    folded = fold(text)
    match = _IDENTITY_NUMBER.search(folded)
    if match:
        number = match.group(1) or match.group(2)
        if number:
            return "cedula", number.replace(".", "")
    # Passport page: avoid matching fiscal "C.I., R.I.F. o PASAPORTE" alone.
    if _PASAPORTE_CARD.search(folded) and "FACTURA" not in folded[:200]:
        pm = _PASSPORT_NUMBER.search(folded)
        if pm:
            return "pasaporte", pm.group(1)
    # Provider/person RIF when no cédula (rare for patients).
    if "CEDULA" not in folded and "C.I" not in folded:
        rm = _RIF_NUMBER.search(folded)
        if rm and rm.group(1) in {"J", "G"}:
            digits = rm.group(2) + (rm.group(3) or "")
            return "rif", f"{rm.group(1)}-{digits}"
    return None


PERSONAL_IDENTITY_TYPES = ("cedula", "pasaporte")


def extract_personal_identity(text: str | None) -> tuple[str, str] | None:
    """Like extract_identity_number, but never a RIF.

    Use this wherever the result may become a person or an invoice titular:
    a RIF on an identity page is the provider/clinic, not the insured.
    """
    found = extract_identity_number(text)
    if found and found[0] in PERSONAL_IDENTITY_TYPES:
        return found
    return None


# Dotted cédula without V/E — common on noisy collage OCR next to card fields.
_DOTTED_CEDULA = re.compile(r"(?<![\d.])(\d{1,2}\.\d{3}\.\d{3})(?![\d.])")
# Bare 7–8 digit cédula near an identity cue (collage OCR often drops the V).
_BARE_CEDULA_NEAR_CUE = re.compile(
    r"(?:CEDULA|C\.?\s*I\.?|VENEZOLAN|NACIONALIDAD|N[°º]\s*DE\s*IDENT)"
    r".{0,40}?(?<![\d.])(\d{7,8})(?![\d.])"
    r"|(?<![\d.])(\d{7,8})(?![\d.]).{0,40}?"
    r"(?:CEDULA|C\.?\s*I\.?|VENEZOLAN|NACIONALIDAD)",
    re.I | re.S,
)
_COLLAGE_OR_CARD = re.compile(
    r"CEDULA\s+DE\s+IDENTIDAD|DOCUMENTOS?\s+DE\s+(?:\S+\s+){0,4}?IDENTIFICACION|"
    r"CONSEJO\s+NACIONAL\s+ELECTORAL|\bAPELLIDOS?\b.+\bNOMBRES?\b",
    re.I | re.S,
)


def extract_all_cedulas(text: str | None) -> list[str]:
    """Every distinct personal cédula on a page, in reading order (digits only).

    Prefers V/E-prefixed and C.I.-labeled matches, then dotted forms, then bare
    digits next to identity cues. Never returns a J/G RIF.
    """
    if not text:
        return []
    folded = fold(text)
    seen: list[str] = []

    def _add(number: str | None) -> None:
        if not number:
            return
        digits = number.replace(".", "").replace(" ", "")
        if len(digits) < 6 or len(digits) > 9:
            return
        # Skip obvious J-RIF tails that slipped past the personal filter.
        if digits.startswith("0") and len(digits) >= 9:
            return
        if digits not in seen:
            seen.append(digits)

    for match in _IDENTITY_NUMBER.finditer(folded):
        _add(match.group(1) or match.group(2))
    for match in _DOTTED_CEDULA.finditer(folded):
        _add(match.group(1))
    if _COLLAGE_OR_CARD.search(folded) or "CEDULA" in folded or "C.I" in folded:
        for match in _BARE_CEDULA_NEAR_CUE.finditer(folded):
            _add(match.group(1) or match.group(2))
    return seen


def extract_name_from_cedula_ocr(text: str | None) -> str | None:
    """Best-effort full name from a photographed cédula or ID collage card block.

    Never returns nationality (Venezolana) or form labels — those fail the name gate.
    """
    from person_name_gate import sanitize_person_name

    if not text:
        return None
    folded = fold(text)
    # Plastic title, CNE header, or collage cover with APELLIDOS/NOMBRES fields.
    if not (
        _CEDULA_TITLE.search(folded)
        or _CEDULA_CNE.search(folded)
        or (_ID_COLLAGE.search(folded) and _CEDULA_CARD_FIELDS.search(folded))
        or (_CEDULA_CARD_FIELDS.search(folded) and extract_all_cedulas(text))
    ):
        return None
    apellidos = None
    nombres = None
    am = _CEDULA_APELLIDOS.search(folded)
    if am:
        apellidos = _normalize_person_name(am.group(1))
    nm = _CEDULA_NOMBRES.search(folded)
    if nm:
        nombres = _normalize_person_name(nm.group(1))
    if apellidos and nombres:
        return sanitize_person_name(f"{nombres} {apellidos}".strip())
    if apellidos:
        return sanitize_person_name(apellidos)
    if nombres:
        return sanitize_person_name(nombres)
    return None


def _normalize_person_name(raw: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
    # Drop bare invoice numbers that ride along in folder names.
    cleaned = re.sub(r"^\d{3,6}\b\s*", "", cleaned)
    cleaned = re.sub(r"\s+\d{3,6}$", "", cleaned)
    parts = []
    for token in cleaned.split():
        upper = fold(token)
        if upper in _NOISE_TOKENS:
            continue
        # Skip invoice-sized numbers; keep longer cédula-like tokens out via callers.
        if re.fullmatch(r"\d{1,6}", token):
            continue
        parts.append(token.title() if token.isupper() or token.islower() else token)
    return " ".join(parts).strip()


def extract_titular_from_path(relative_path: str) -> tuple[str | None, str | None]:
    """Return (full_name, cédula_digits) for the invoice titular from path/folder names.

    The person for each invoice is the titular. Paths often encode that name after
    the FACT number, sometimes with a cédula. Returns (None, None) when absent.
    Prefer FACT-labeled segments. Require a two-word name unless a cédula is present
    so org folders (CORPOELEC) and bare first names are not treated as the client.
    """
    path = Path(relative_path)
    parts = [path.stem, *[part for part in path.parts[:-1][::-1]]]
    # FACT-labeled stems/folders first — those usually carry the titular.
    candidates = sorted(
        parts,
        key=lambda raw: (0 if _FACT_PREFIX.search(raw or "") else 1, -len(raw or "")),
    )
    best_name = None
    best_cedula = None
    for raw in candidates:
        folded = fold(raw)
        cedula = None
        cedula_match = _PATH_CEDULA.search(folded.replace(",", " "))
        if cedula_match:
            cedula = re.sub(r"\D", "", cedula_match.group(1))
            if len(cedula) < 6:
                cedula = None
        text = raw
        text = _FACT_PREFIX.sub("", text)
        text = _ROLE_PREFIX.sub("", text)
        # Drop a leading invoice number glued to the name (7394LUIS → LUIS).
        text = re.sub(r"^\d{3,6}(?=[A-Za-zÁÉÍÓÚÑáéíóúñ])", "", text)
        # Drop a trailing dotted cédula from the name span.
        text = re.sub(r"(?:V|E)?\s*-?\s*\d{1,2}(?:[.\s]\d{3}){2}\s*$", "", text, flags=re.I)
        text = re.sub(r"(?:V|E)?\s*-?\s*\d{6,9}\s*$", "", text, flags=re.I)
        name = _normalize_person_name(text)
        tokens = name.split() if name else []
        # Batch folders like "FACTURAS … NOVIEMBRE LOTE …" normalize to empty
        # once months/FACTURAS are noise — skip them.
        if len(tokens) >= 2:
            return name, cedula
        if cedula and not best_cedula:
            best_cedula = cedula
            if name:
                best_name = name
        # Single token without cédula is not enough to identify the titular.
    if best_cedula:
        return best_name, best_cedula
    return None, None


def extract_titular_from_ocr(text: str | None) -> tuple[str | None, str | None]:
    """Return (full_name, cédula_digits) from invoice OCR when the Titular line is readable."""
    if not text:
        return None, None
    folded = fold(text)
    name = None
    match = _TITULAR_OCR.search(folded)
    if match:
        name = _normalize_person_name(match.group(1))
        if not name:
            name = None
    identity = extract_identity_number(text)
    # A RIF on the fiscal page is the provider or tomador company, never the titular.
    cedula = identity[1] if identity and identity[0] == "cedula" else None
    return name, cedula


def account_code_from_label(label: str) -> str | None:
    if not label or label in ("mixed", "(no account token)", "(blank)"):
        return None
    mapping = {
        "La Previsora": "la_previsora",
        "Altamira": "altamira",
        "Latitud": "latitud",
        "Seguros Miranda": "seguros_miranda",
        "Constitucion": "constitucion",
        "SENIAT": "seniat",
        "Hispana": "hispana",
        "Cemento Andino": "cemento_andino",
        "Seguros Venezuela": "seguros_venezuela",
        "FASMEE": "fasmee",
        "Corporacion": "corporacion",
        "Piramide": "piramide",
        "SAREN": "saren",
        "CORPOELEC": "corpoelec",
        "Bicentenario": "bicentenario",
        "Cuidamed": "cuidamed",
        "CANTV": "cantv",
        "Pueblo Soberano": "pueblo_soberano",
    }
    return mapping.get(label)
