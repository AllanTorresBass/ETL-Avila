"""Canonical row fields and header alias map for register workbooks."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Target fields produced by normalize.row_from_headers
CANONICAL_FIELDS = (
    "titular_name",
    "titular_ci",
    "beneficiario_name",
    "beneficiario_ci",
    "birth_date",
    "beneficiario_birth_date",
    "parentesco",
    "phone",
    "beneficiario_phone",
    "address",
    "clave_rms",
    "contratante",
    "diagnosis",
    "service_description",
    "provider_name",
    "provider_rif",
    "amount_bs",
    "amount_usd",
    "coverage_amount",
    "authorized_amount",
    "invoice_number",
    "control_number",
    "service_date",
    "request_date",
    "issue_date",
)


def fold_header(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().strip()
    text = re.sub(r"\s+", " ", text)
    return text


# Folded header → canonical field. First match wins when scanning columns left→right
# for duplicate labels (e.g. two CEDULA DE IDENTIDAD columns).
HEADER_ALIASES: dict[str, str] = {
    # Titular
    "TITULAR": "titular_name",
    "NOMBRE TITULAR": "titular_name",
    "NOMBRE DEL TITULAR": "titular_name",
    "CI TITULAR": "titular_ci",
    "C.I. TITULAR": "titular_ci",
    "C.I TITULAR": "titular_ci",
    "CEDULA DE IDENTIDAD": "titular_ci",  # first occurrence → titular
    # Beneficiario / paciente
    "BENEFICIARIO": "beneficiario_name",
    "NOMBRE DEL PACIENTE": "beneficiario_name",
    "CI BENEFICIARIO": "beneficiario_ci",
    "C.I. PACIENTE": "beneficiario_ci",
    "C.I PACIENTE": "beneficiario_ci",
    # Demographics
    "FECHA DE NACIMIENTO": "birth_date",
    "PARENTESCO": "parentesco",
    "TELEFONO": "phone",
    "TELEFONO CONTACTO BENEFICIARIO (EMERGENCIAS)": "beneficiario_phone",
    "TELF.ASEGURADO": "phone",
    "TELF ASEGUARADO": "phone",
    "DIRECCION": "address",
    # Authorization / service
    "CLAVE RMS": "clave_rms",
    "CLAVE DE AUTORIZACION": "clave_rms",
    "CLAVE DE AUTORIZACIÓN": "clave_rms",
    "NRO DE COMPROMISOS DE CLAVE": "clave_rms",
    "AUTORIZACION": "clave_rms",
    "CONTRATANTE": "contratante",
    "EMPRESA /O INSTITUCION": "contratante",
    "EMPRESA / O INSTITUCION": "contratante",
    "INSTITUCION": "contratante",
    "DIAGNOSTICO": "diagnosis",
    "DIAGNÓSTICO": "diagnosis",
    "SINTOMA / DIAGNOSTICO": "diagnosis",
    "DESCRPCION DE SERVICIOS": "service_description",
    "DESCRIPCION DE SERVICIOS": "service_description",
    "DESCRIPCION DE SERVICIOS MEDICOS": "service_description",
    "PROVEEDOR": "provider_name",
    "NOMBRE DEL PROVEEDOR": "provider_name",
    "RAZON SOCIAL": "provider_name",
    "RIF": "provider_rif",
    "RIF. DEL PROVEEDOR": "provider_rif",
    "RIF DEL PROVEEDOR": "provider_rif",
    # Amounts
    "MONTO BOLIVARES": "amount_bs",
    "MONTO BS": "amount_bs",
    "MONTO DE PPTO. O MONTO FACTURADO": "amount_bs",
    "MONTO FACTURADO": "amount_bs",
    "TOTAL": "amount_bs",
    "MONTO $": "amount_usd",
    "MONTO USD": "amount_usd",
    "MONTO COBERTURA SEGUROS MIRANDA": "coverage_amount",
    "MONTO AUTORIZADO": "authorized_amount",
    "BAREMO APROBADO": "authorized_amount",
    "MONTO TOTAL SOLICITADO": "amount_bs",
    # Invoice / dates
    "NRO DE FACTURA": "invoice_number",
    "NRO. DE FACTURA": "invoice_number",
    "NRO DE CONTROL": "control_number",
    "FECHA DE FACTURA": "issue_date",
    "FECHA FACTURA": "issue_date",
    "FECHA DE SERVICIO": "service_date",
    "FECHA DE ATENCION": "service_date",
    "FECHA CITA": "service_date",
    "FECHA DE LA CITA": "service_date",
    "FECHA RECIBIDO": "request_date",
    "FECHA DE SOLICITUD": "request_date",
    "FECHA DEL DIA DE LA SOLICITUD": "request_date",
}

# Families we intentionally skip (price lists / templates / budgets)
SKIP_PATH_RE = re.compile(
    r"(BAREMO|BAREMOS|PLANTILLA|FORMATO\s+FACTURA|FORMATO\s+INSUMOS|"
    r"PRESUPUESTO\s+\d|CONTRA\s*OFERTA|SENIAT\s+2025)",
    re.IGNORECASE,
)

FAMILY_PATH_HINTS = (
    ("sabana", re.compile(r"SABANA", re.I)),
    ("claves", re.compile(r"CLAVES?|GPS\s+AVILA\s+\d", re.I)),
    ("cintillo", re.compile(r"CINTILLO", re.I)),
    ("relacion", re.compile(r"RELACION|SOLICITUD\s+SERVICIOS", re.I)),
    ("amp", re.compile(r"AMP\s*\(|SERVICIO\s+INMEDIATO", re.I)),
    ("estado_cuenta", re.compile(r"ESTADO\s+DE\s+CUENTA", re.I)),
)


def guess_family(path: str, headers: list[str]) -> str:
    for name, pattern in FAMILY_PATH_HINTS:
        if pattern.search(path):
            return name
    folded = [fold_header(h) for h in headers if h]
    if any("CLAVE RMS" in h for h in folded) and any("TITULAR" in h for h in folded):
        if any("TELEFONO CONTACTO" in h for h in folded) or any(h == "MONTO $" for h in folded):
            return "claves"
        return "sabana"
    if any("NRO DE FACTURA" in h for h in folded) and any("BENEFICIARIO" in h for h in folded):
        return "relacion"
    if any("NOMBRE TITULAR" in h or "NOMBRE DEL TITULAR" in h for h in folded):
        return "cintillo"
    if any("C.I. TITULAR" in h or "NOMBRE DEL PACIENTE" in h for h in folded):
        return "amp"
    return "unknown"
