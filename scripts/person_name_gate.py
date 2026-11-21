"""Reject OCR / path strings that are not a real person name.

A usable name is two to five tokens, each with a vowel and a consonant.
Nationality lines (Venezolana), form labels (Apellidos, Cédula), dates, and
clinical crumbs are rejected so they never become ``person.full_name``.
"""

from __future__ import annotations

import re

from invoice_rules import fold

# Whole-token rejects (``fold()`` returns uppercase without accents).
_REJECT_TOKENS = frozenset(
    {
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
        "PASAPORTE",
        "CARNET",
        "SOLTERO",
        "SOLTERA",
        "CASADO",
        "CASADA",
        "FEMENINO",
        "MASCULINO",
        "RIF",
        "FACTURA",
        "FACTURAS",
        "TITULAR",
        "BENEFICIARIO",
        "PACIENTE",
        "IDOS",  # OCR crumb from "Apellidos"
    }
)

_REJECT_SUBSTRING = re.compile(
    r"venezolan|nacionalidad|cedula\s+de\s+identidad|apellidos?\b.*nombres?|"
    r"estado\s+civil|fecha\s+de\s+nacimiento",
    re.I,
)

_DATE_AS_NAME = re.compile(r"^20[2-3]\d{5}\b")
_VOWEL = re.compile(r"[AEIOUÁÉÍÓÚÜaeiouáéíóúü]")
_CONSONANT = re.compile(r"[BCDFGHJKLMNÑPQRSTVWXYZbcdfghjklmnñpqrstvwxyz]")


def _strip_punct(token: str) -> str:
    return re.sub(r"[^\wÁÉÍÓÚÑáéíóúñüÜ]", "", token, flags=re.UNICODE)


def _cleaned_tokens(name: str) -> list[str] | None:
    """Return kept name tokens, or None when the string is not usable."""
    text = " ".join(str(name).split()).strip(" .,-;:/|*+<>!")
    if not text or _DATE_AS_NAME.match(text):
        return None
    raw_tokens = [_strip_punct(t) for t in text.replace("/", " ").split()]
    tokens = [t for t in raw_tokens if t]
    if len(tokens) < 2 or len(tokens) > 8:
        return None
    kept: list[str] = []
    for token in tokens:
        folded = fold(token)
        if folded in _REJECT_TOKENS or folded.startswith("VENEZOLAN"):
            continue
        if folded.isdigit() or len(folded) == 1:
            continue
        if not _VOWEL.search(token) or not _CONSONANT.search(token):
            if folded in {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E"}:
                kept.append(token)
            continue
        kept.append(token)
    content = [t for t in kept if fold(t) not in {"DE", "DEL", "LA", "LAS", "LOS", "Y", "E"}]
    if len(content) < 2:
        return None
    return kept


def is_usable_person_name(name: str | None) -> bool:
    """True when ``name`` looks like a real person (not OCR nationality/label noise)."""
    if not name or not str(name).strip():
        return False
    return _cleaned_tokens(str(name)) is not None


def sanitize_person_name(name: str | None) -> str | None:
    """Return a cleaned usable name, or ``None`` (do not write junk)."""
    if name is None:
        return None
    kept = _cleaned_tokens(str(name))
    if not kept:
        return None
    return " ".join(kept)


def is_date_like_identity(identity_number: str | None) -> bool:
    """Scan-batch folder dates (YYYYMMDD, 8 digits) are not cédulas."""
    if not identity_number:
        return False
    digits = re.sub(r"\D", "", identity_number)
    return bool(re.fullmatch(r"20[2-3]\d{5}", digits))
