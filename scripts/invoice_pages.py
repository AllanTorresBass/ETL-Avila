"""Decide whether one OCR'd page is the fiscal invoice sheet.

The decision uses keyword evidence only. Callers should not store patient
lines from the OCR text in the inventory.
"""

from __future__ import annotations

import re

from invoice_rules import fold

_HEADING = re.compile(r"FACTUR")
_NUMERO = re.compile(r"N[°ºO.]{0,2}\s*(RO\.?)?\s*(DE\s+)?FACTUR|NUMERO\s+DE\s+FACTUR|\bNRO\b")
_RIF = re.compile(r"\bJ\s*-?\s*\d{7,9}\b|\bRIF\b")
_CONTROL = re.compile(r"CONTROL")
_FORMA = re.compile(r"\bFORMA\b")
_ORIGINAL = re.compile(r"\bORIGINAL\b")
_COMPROBANTE = re.compile(r"\bCOMPROBANTE\b")
_INFORME = re.compile(r"\bINFORME\b")
_CLINICAL = re.compile(r"\b(EGRESO|INGRESO|LABORATORIO|RAYOS|ECOGRAF|HEMATOLOGI)\b")
# Printed on the forma libre footer. Attachment pages in this backup do not carry it.
_CREDITO_FISCAL = re.compile(r"\bCREDITO\s+FISCAL\b")
_FORMA_LIBRE = re.compile(r"\bFORMA\s+LIBRE\b")
# OCR glues "N° DE CONTROL" into one token. A bare CONTROL also appears on slips.
_DECONTROL = re.compile(r"DECONTROL")
# Insurer claim forms print "FACTURA N°" boxes and the provider RIF but are not
# the fiscal sheet.
_CLAIM_FORM = re.compile(
    r"LARACION\s+DE\s+SINIESTRO|SOLICITUD\s+(?:DE\s+)?CARTA\s+AVAL|"
    r"SOLICITUD\s+DE\s+REEMBOLSO|PLANILLA\s+DE\s+(?:SINIESTRO|REEMBOLSO|RECLAMO)|"
    r"\bNO\.?\s*RECLAMO\b|NRO\s+PPTO\s*/\s*FACTURA"
)


def judge_page(text: str) -> tuple[str, str]:
    """Return (label, evidence).

    label is fiscal_invoice, attachment, or unreadable.
    evidence names the matched tokens and does not quote the page.

    The fiscal sheet is the forma libre: it carries FACTURA, N° DE CONTROL
    together with FORMA / ORIGINAL, the forma libre title, or the crédito
    fiscal footer. A RIF alone is only the letterhead, so informes and
    comprobantes that repeat the provider RIF stay attachments.
    """
    if text is None:
        return "unreadable", "empty_ocr"
    folded = fold(text)
    if not folded.strip():
        return "unreadable", "empty_ocr"
    heading = bool(_HEADING.search(folded))
    numero = bool(_NUMERO.search(folded))
    rif = bool(_RIF.search(folded))
    # OCR often glues "N° DE CONTROL" into "DECONTROL".
    control = bool(_CONTROL.search(folded))
    forma = bool(_FORMA.search(folded))
    original = bool(_ORIGINAL.search(folded))
    forma_libre = forma or original
    # A preliquidación cites the invoice number. It is not the fiscal sheet
    # unless it also carries the forma libre markers.
    if _CLAIM_FORM.search(folded) and not (_CREDITO_FISCAL.search(folded) or _FORMA_LIBRE.search(folded)):
        return "attachment", "claim_form"
    if _COMPROBANTE.search(folded) and not forma_libre:
        return "attachment", "comprobante"
    if _INFORME.search(folded) and not (control and forma_libre):
        return "attachment", "informe"
    if heading and (numero or rif or control):
        bits = ["heading:FACTURA"]
        if numero:
            bits.append("numero")
        if control:
            bits.append("control")
        if rif:
            bits.append("rif")
        return "fiscal_invoice", "+".join(bits)
    # The FACTURA box is often a graphic. CONTROL plus FORMA LIBRE / ORIGINAL
    # is the same fiscal sheet.
    if control and forma_libre:
        bits = ["control"]
        if forma:
            bits.append("forma")
        if original:
            bits.append("original")
        return "fiscal_invoice", "+".join(bits)
    # Some scans never read the FACTURA box. The footer and the forma libre
    # title are still specific to that sheet.
    if _CREDITO_FISCAL.search(folded):
        return "fiscal_invoice", "credito_fiscal"
    if _FORMA_LIBRE.search(folded):
        return "fiscal_invoice", "forma_libre"
    if _DECONTROL.search(folded):
        return "fiscal_invoice", "decontrol"
    if heading:
        return "attachment", "heading_without_fiscal_token"
    if _CLINICAL.search(folded):
        return "attachment", "clinical_terms"
    return "attachment", "no_factura_heading"
