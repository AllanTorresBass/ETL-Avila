"""Normalize workbook cells into canonical person / authorization fields."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .canonical import HEADER_ALIASES, fold_header

_CI_RE = re.compile(r"(?:V|E)?\s*-?\s*(\d{1,2}(?:[.\s]\d{3}){2}|\d{6,9})\b", re.I)
_FACT_RE = re.compile(r"(?:FACT(?:URA)?|FAC)?\s*(\d{3,6})\b", re.I)


def digits_ci(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            n = int(value)
            if n <= 0:
                return None
            return str(n)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "-"}:
        return None
    m = _CI_RE.search(text.replace(",", ""))
    if not m:
        # bare digits
        digits = re.sub(r"\D", "", text)
        if 6 <= len(digits) <= 9:
            return digits.lstrip("0") or digits
        return None
    raw = m.group(1)
    digits = re.sub(r"\D", "", raw)
    if 6 <= len(digits) <= 9:
        return digits.lstrip("0") or digits
    return None


_EMPTY_LABELS = {
    "none",
    "nan",
    "-",
    "n/a",
    "no llenar",
    "s/n",
    "sn",
    "null",
}


def _clean_parentesco(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_LABELS:
        return None
    return text[:40]


def clean_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_LABELS:
        return None
    text = re.sub(r"\s+", " ", text)
    if len(text) < 3:
        return None
    return text[:120]


def parse_date(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial (Windows epoch)
        try:
            base = dt.datetime(1899, 12, 30)
            return (base + dt.timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace("Bs.", "").replace("Bs.S", "").replace("$", "")
    text = text.replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {".", "-", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_invoice_number(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    m = _FACT_RE.search(text)
    if m:
        return str(int(m.group(1)))
    digits = re.sub(r"\D", "", text)
    if 3 <= len(digits) <= 6:
        # Workbooks often pad FACT as 004277; Neon stores 4277.
        return str(int(digits))
    return None


def map_headers(headers: list[Any]) -> dict[int, str]:
    """Map column index → canonical field.

    Duplicate CEDULA → beneficiario_ci on 2nd hit. A FECHA DE NACIMIENTO column
    belongs to whoever's columns precede it: after BENEFICIARIO / CI BENEFICIARIO
    it is the beneficiary's (Miranda sábanas have only that one), otherwise the
    titular's. ``birth_date`` therefore always means the titular's DOB.
    """
    out: dict[int, str] = {}
    seen_ci_label = 0
    seen_beneficiario = False
    for idx, header in enumerate(headers):
        folded = fold_header(header)
        if not folded:
            continue
        field = HEADER_ALIASES.get(folded)
        if folded == "CEDULA DE IDENTIDAD":
            seen_ci_label += 1
            field = "titular_ci" if seen_ci_label == 1 else "beneficiario_ci"
        elif folded == "FECHA DE NACIMIENTO":
            field = "beneficiario_birth_date" if seen_beneficiario else "birth_date"
        if field in {"beneficiario_name", "beneficiario_ci"}:
            seen_beneficiario = True
        if not field:
            continue
        if field in out.values() and field not in {
            "titular_ci",
            "beneficiario_ci",
            "birth_date",
            "beneficiario_birth_date",
        }:
            # keep first occurrence for most fields
            continue
        out[idx] = field
    return out


def row_dict(headers: list[Any], values: list[Any]) -> dict[str, Any]:
    mapping = map_headers(headers)
    raw: dict[str, Any] = {}
    for idx, field in mapping.items():
        if idx >= len(values):
            continue
        raw[field] = values[idx]

    titular_ci = digits_ci(raw.get("titular_ci"))
    beneficiario_ci = digits_ci(raw.get("beneficiario_ci"))
    # If only one CI column was mapped as titular but value looks empty and
    # beneficiario filled — keep as-is.

    birth = parse_date(raw.get("birth_date"))
    ben_birth = parse_date(raw.get("beneficiario_birth_date"))

    return {
        "titular_name": clean_name(raw.get("titular_name")),
        "titular_ci": titular_ci,
        "beneficiario_name": clean_name(raw.get("beneficiario_name")),
        "beneficiario_ci": beneficiario_ci,
        "birth_date": birth,
        "beneficiario_birth_date": ben_birth,
        "parentesco": _clean_parentesco(raw.get("parentesco")),
        "phone": clean_name(raw.get("phone")),
        "beneficiario_phone": clean_name(raw.get("beneficiario_phone")),
        "address": clean_name(raw.get("address")),
        "clave_rms": clean_name(raw.get("clave_rms")),
        "contratante": clean_name(raw.get("contratante")),
        "diagnosis": clean_name(raw.get("diagnosis")),
        "service_description": clean_name(raw.get("service_description")) or clean_name(raw.get("service_type")),
        "service_type": clean_name(raw.get("service_type")),
        "aps_code": clean_name(raw.get("aps_code")),
        "provider_name": clean_name(raw.get("provider_name")),
        "provider_rif": clean_name(raw.get("provider_rif")),
        "amount_bs": parse_amount(raw.get("amount_bs")),
        "amount_usd": parse_amount(raw.get("amount_usd")),
        "coverage_amount": parse_amount(raw.get("coverage_amount")),
        "authorized_amount": parse_amount(raw.get("authorized_amount")),
        "invoice_number": parse_invoice_number(raw.get("invoice_number")),
        "control_number": clean_name(raw.get("control_number")),
        "service_date": parse_date(raw.get("service_date")),
        "request_date": parse_date(raw.get("request_date")),
        "issue_date": parse_date(raw.get("issue_date")),
    }


def row_has_person_signal(row: dict[str, Any]) -> bool:
    return bool(
        row.get("titular_ci")
        or row.get("beneficiario_ci")
        or row.get("titular_name")
        or row.get("beneficiario_name")
        or row.get("clave_rms")
        or row.get("invoice_number")
    )
