"""Pull birth date, phone, and address candidates from one OCR page or workbook cell.

Pure functions. No database and no PHI logging. Callers bind a candidate to a
person, then fill only an empty field.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from document_types import extract_all_cedulas
from invoice_rules import fold
from person_upsert import fold_person_name

ID_TYPES = {
    "cedula_identidad",
    "documentos_identificacion",
    "carnet",
    "pasaporte",
}
FORM_TYPES = {
    "informe_medico",
    "comprobante",
    "carta_aval",
    "ingreso",
    "egreso",
    "orden_servicio",
    "otro_anexo",
}

_MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

_DOB_LABEL = re.compile(r"F\.?\s*NACIMIENTO|FECHA\s+(?:DE\s+)?NACIMIENTO|NACIO\s+EL")
_DATE_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_DATE_LONG = re.compile(r"\b(\d{1,2})\s+DE\s+([A-Z]+)\s+DE(?:L)?\s+(\d{4})\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?58[\s\-]?)?(?:0?[24]\d{2})[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)"
)
_PHONE_LABEL = re.compile(r"TELEFONO|TELF\.?|CELULAR|CEL\.")
_ADDR_LABEL = re.compile(r"DOMICILIO|DIRECCION")
_LETTERHEAD = re.compile(r"CLINICA|HOSPITAL|SEGUROS|TOMADOR|\bRIF\b|CENTRO\s+MEDICO")
_PATIENT = re.compile(r"PACIENTE|ASEGURADO|TITULAR|BENEFICIARIO|NOMBRE")
_PARENT = re.compile(r"\b(?:PADRE|MADRE|PRESENTANTE)\b")
_CLINIC_ADDR = re.compile(r"^(?:CLINICA|HOSPITAL|CENTRO MEDICO|SEGUROS|RIF)\b")
_NAME_LABEL = re.compile(
    r"(?:NOMBRE\s+DEL\s+PACIENTE|PACIENTE|ASEGURADO|TITULAR|BENEFICIARIO|NOMBRE)\s*[:\-]\s*"
    r"([A-Z][A-Z ]{4,70})"
)
_NAME_STOP = re.compile(r"\b(?:TEL|CEDULA|C\.?\s*I|FECHA|EDAD|SEXO|PARENTESCO|DOMICILIO|DIRECCION)\b")
_CUE_DOB = re.compile(r"NACIMIENTO|NACIO\s+EL")
_CUE_PHONE = re.compile(r"TELEFONO|TELF|CELULAR")
_CUE_ADDR = re.compile(r"DIRECCION|DOMICILIO")


@dataclass(frozen=True)
class Candidate:
    field: str
    value: object
    rule_id: str
    confidence: float
    block_ci: str | None = None
    block_name: str | None = None


@dataclass
class PageExtract:
    candidates: list[Candidate] = field(default_factory=list)
    cues: set[str] = field(default_factory=set)
    rejected_letterhead: bool = False


@dataclass(frozen=True)
class PersonOnInvoice:
    person_id: str
    full_name: str | None
    identity_number: str | None
    role: str
    parentesco: str | None = None


def page_cues(text: str | None) -> set[str]:
    folded = fold(text or "")
    cues: set[str] = set()
    if _CUE_DOB.search(folded):
        cues.add("birth_date")
    if _CUE_PHONE.search(folded):
        cues.add("phone")
    if _CUE_ADDR.search(folded):
        cues.add("address")
    return cues


def plausible_dob(value: dt.date, *, today: dt.date | None = None) -> bool:
    if value.year < 1915 or value.year in {1899, 1900}:
        return False
    today = today or dt.date.today()
    if value > today:
        return False
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    return 0 <= age <= 110


def _try_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_dates(fragment: str, *, today: dt.date | None = None) -> list[dt.date]:
    found: list[dt.date] = []
    for match in _DATE_NUMERIC.finditer(fragment):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        value = _try_date(year, month, day)
        if value and plausible_dob(value, today=today) and value not in found:
            found.append(value)
    for match in _DATE_LONG.finditer(fragment):
        month = _MONTHS.get(match.group(2))
        if not month:
            continue
        value = _try_date(int(match.group(3)), month, int(match.group(1)))
        if value and plausible_dob(value, today=today) and value not in found:
            found.append(value)
    return found


def canonical_phone(raw: str | None) -> str | None:
    """Venezuelan mobile or landline as 11 digits starting with 0."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0058"):
        digits = digits[4:]
    elif digits.startswith("58") and len(digits) >= 12:
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "24":
        digits = "0" + digits
    if len(digits) != 11 or digits[0] != "0" or digits[1] not in "24":
        return None
    if len(set(digits)) == 1:
        return None
    return digits


def phones_in_text(text: str | None) -> list[str]:
    found: list[str] = []
    for match in _PHONE.finditer(fold(text or "")):
        number = canonical_phone(match.group(0))
        if number and number not in found:
            found.append(number)
    return found


def clean_address(value: str | None, *, min_len: int = 8) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip(" .,:-|")
    if len(text) < min_len:
        return None
    text = text[:180]
    if _CLINIC_ADDR.match(fold(text)):
        return None
    return text


def same_address(left: str, right: str) -> bool:
    a, b = fold(left), fold(right)
    if a == b:
        return True
    if len(a) >= 12 and len(b) >= 12 and (a in b or b in a):
        return True
    return False


def same_value(field_name: str, left: object, right: object) -> bool:
    if field_name == "phone":
        return canonical_phone(str(left)) == canonical_phone(str(right)) and canonical_phone(str(left)) is not None
    if field_name == "address":
        return same_address(str(left), str(right))
    return left == right


def names_compatible(left: str | None, right: str | None) -> bool:
    """True when the shorter name's tokens are all in the longer one, both at least two tokens."""
    tokens_a = fold_person_name(left or "").split()
    tokens_b = fold_person_name(right or "").split()
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return False
    set_a, set_b = set(tokens_a), set(tokens_b)
    shorter, longer = (set_a, set_b) if len(set_a) <= len(set_b) else (set_b, set_a)
    return shorter <= longer


def is_minor_beneficiario(
    role: str | None,
    parentesco: str | None,
    birth_date: dt.date | None = None,
    *,
    today: dt.date | None = None,
) -> bool:
    if role != "beneficiario":
        return False
    label = fold(parentesco or "").replace(" ", "")
    if re.match(r"^HIJ[OA]S?$", label) or "MENOR" in label:
        return True
    if birth_date:
        today = today or dt.date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age < 18
    return False


def _nearest_ci(folded: str, pos: int) -> str | None:
    window = folded[max(0, pos - 350) : pos + 40]
    found = extract_all_cedulas(window)
    return found[-1] if found else None


def _capture_name(window: str) -> str | None:
    match = _NAME_LABEL.search(window)
    if not match:
        return None
    raw = _NAME_STOP.split(match.group(1))[0]
    tokens = [token for token in raw.split() if token][:6]
    if len(tokens) < 2:
        return None
    return " ".join(tokens)


def _name_around(folded: str, pos: int) -> str | None:
    return _capture_name(folded[max(0, pos - 220) : pos]) or _capture_name(folded[pos : pos + 180])


def _letterhead(window: str) -> bool:
    return bool(_LETTERHEAD.search(window) and not _PATIENT.search(window))


def _dates_after(folded: str, pos: int, *, today: dt.date | None) -> list[dt.date]:
    return parse_dates(folded[pos : pos + 80], today=today)


def _add_dob(out: list[Candidate], value: dt.date, rule_id: str, confidence: float, *, ci: str | None = None, name: str | None = None) -> None:
    out.append(Candidate("birth_date", value, rule_id, confidence, block_ci=ci, block_name=name))


def extract_page(text: str | None, document_type: str, *, today: dt.date | None = None) -> PageExtract:
    folded = fold(text or "")
    result = PageExtract(cues=page_cues(folded))
    if not folded or document_type in {"ilegible", "factura_fiscal"}:
        return result

    if document_type in ID_TYPES:
        for match in _DOB_LABEL.finditer(folded):
            dates = _dates_after(folded, match.end(), today=today)
            if not dates:
                continue
            ci = _nearest_ci(folded, match.start())
            _add_dob(result.candidates, dates[0], "cedula_dob", 0.9 if ci else 0.8, ci=ci)
        return result

    if document_type == "acta_nacimiento":
        for match in _DOB_LABEL.finditer(folded):
            before = folded[max(0, match.start() - 180) : match.start()]
            if _PARENT.search(before):
                continue
            dates = _dates_after(folded, match.end(), today=today)
            if dates:
                _add_dob(result.candidates, dates[0], "acta_child_dob", 0.85)
                break
        for match in _ADDR_LABEL.finditer(folded):
            address = clean_address(_address_slice(folded, match.end()))
            if address:
                result.candidates.append(Candidate("address", address, "acta_domicilio", 0.75))
                break
        return result

    if document_type not in FORM_TYPES:
        return result

    for match in _DOB_LABEL.finditer(folded):
        dates = _dates_after(folded, match.end(), today=today)
        if not dates:
            continue
        ci = _nearest_ci(folded, match.start())
        name = _name_around(folded, match.start())
        _add_dob(result.candidates, dates[0], "form_dob", 0.7, ci=ci, name=name)

    for match in _PHONE_LABEL.finditer(folded):
        window = folded[max(0, match.start() - 80) : match.end() + 70]
        if _letterhead(window):
            result.rejected_letterhead = True
            continue
        numbers = phones_in_text(folded[match.end() : match.end() + 70])
        if not numbers:
            continue
        ci = _nearest_ci(folded, match.start())
        name = _name_around(folded, match.start())
        for number in numbers:
            confidence = 0.8 if number[1] == "4" else 0.6
            result.candidates.append(
                Candidate("phone", number, "informe_phone", confidence, block_ci=ci, block_name=name)
            )

    for match in _ADDR_LABEL.finditer(folded):
        window = folded[max(0, match.start() - 40) : match.end() + 40]
        if _letterhead(window):
            result.rejected_letterhead = True
            continue
        address = clean_address(_address_slice(folded, match.end()))
        if not address:
            continue
        ci = _nearest_ci(folded, match.start())
        name = _name_around(folded, match.start())
        result.candidates.append(Candidate("address", address, "form_address", 0.7, block_ci=ci, block_name=name))
    return result


def _address_slice(folded: str, pos: int) -> str:
    window = folded[pos : pos + 160]
    window = re.split(r"\b(?:TELEFONO|TELF|CEDULA|C\.I|FECHA|PARENTESCO|CORREO|EMAIL)\b", window)[0]
    return window


def bind_candidate(
    candidate: Candidate,
    people: list[PersonOnInvoice],
    *,
    blocked: bool = False,
    persons_by_ci: dict[str, str] | None = None,
    hint_person_id: str | None = None,
    hint_role: str | None = None,
    sole_dob: bool = False,
) -> tuple[str | None, str]:
    """Return (person_id, status). Status is bound, ambiguous, or blocked_review."""
    if candidate.block_ci:
        person_id = (persons_by_ci or {}).get(candidate.block_ci)
        if not person_id:
            hits = [p.person_id for p in people if p.identity_number == candidate.block_ci]
            person_id = hits[0] if len(hits) == 1 else None
        if person_id:
            return person_id, "bound"
        return None, "ambiguous"
    if blocked:
        return None, "blocked_review"
    if candidate.block_name:
        hits: list[str] = []
        for person in people:
            if person.full_name and names_compatible(candidate.block_name, person.full_name):
                if person.person_id not in hits:
                    hits.append(person.person_id)
        if len(hits) == 1:
            return hits[0], "bound"
        return None, "ambiguous"
    if candidate.rule_id == "acta_child_dob":
        if hint_person_id and hint_role == "beneficiario":
            return hint_person_id, "bound"
        bens = []
        for person in people:
            if person.role == "beneficiario" and person.person_id not in bens:
                bens.append(person.person_id)
        if len(bens) == 1:
            return bens[0], "bound"
        return None, "ambiguous"
    if candidate.rule_id == "acta_domicilio":
        if hint_person_id and hint_role == "titular":
            return hint_person_id, "bound"
        tits = []
        for person in people:
            if person.role == "titular" and person.person_id not in tits:
                tits.append(person.person_id)
        if len(tits) == 1:
            return tits[0], "bound"
        return None, "ambiguous"
    if candidate.rule_id == "cedula_dob" and sole_dob and hint_person_id:
        return hint_person_id, "bound"
    return None, "ambiguous"
