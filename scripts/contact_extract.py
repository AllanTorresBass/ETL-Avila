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
_DATE_SHORT = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})(?!\d)")
_DATE_LONG = re.compile(r"\b(\d{1,2})\s+DE\s+([A-Z]+)\s+DE(?:L)?\s+(\d{4})\b")
_DATE_ABBR = re.compile(r"\b(\d{1,2})\s+([A-Z]{3,9})\.?\s+(\d{4})\b")
_MONTH_ABBR = {
    "ENE": 1,
    "FEB": 2,
    "MAR": 3,
    "ABR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SEP": 9,
    "SET": 9,
    "OCT": 10,
    "NOV": 11,
    "DIC": 12,
}
_PHONE_SPLIT = re.compile(r"[^0-9+\s\-.()]+")
_PHONE_LABEL = re.compile(r"TELEFONO|TELF\.?|CELULAR|CEL\.")
_ADDR_LABEL = re.compile(r"DOMICILIO|DIRECCION")
_LETTERHEAD = re.compile(r"CLINICA|HOSPITAL|SEGUROS|TOMADOR|\bRIF\b|CENTRO\s+MEDICO")
_PATIENT = re.compile(r"PACIENTE|ASEGURADO|TITULAR|BENEFICIARIO|NOMBRE")
_PARENT = re.compile(r"\b(?:PADRE|MADRE|PRESENTANTE)\b")
_CLINIC_ADDR = re.compile(
    r"\b(?:CLINICA|HOSPITAL|CENTRO\s+MEDICO|CENTRO\s+CLINICO|SEGUROS|RIF)\b"
)
_STREET_TOKEN = re.compile(
    r"\b(?:CALLE|AVENIDA|AV|URBANIZACION|URB|SECTOR|VEREDA|EDIFICIO|EDIF|"
    r"RESIDENCIA|QUINTA|PARROQUIA|MANZANA)\b\.?"
)
_STREET_NUM = re.compile(
    r"\b(CALLE|AVENIDA|AV|URBANIZACION|URB|SECTOR|VEREDA|EDIFICIO|EDIF|"
    r"RESIDENCIA|QUINTA|PARROQUIA|MANZANA)\.?\s+(\d+)"
)
_STREET_ALIAS = {"AV": "AVENIDA", "URB": "URBANIZACION", "EDIF": "EDIFICIO"}
_NOT_HOME = re.compile(
    r"\b(?:DIAGNOSTICO|OJO|CORNEA|CIRUGIA|LENTE|TRATAMIENTO|AGUDEZA|RETINA|"
    r"CATARATA|GLAUCOMA|CONJUNTIVA|PARPADO|QUIROFANO|LABORATORIO|HEMOGRAMA|"
    r"CONSULTORIO|SEDE|OFTALMOLOG\w*|INSTITUTO|VENEZUELA)\b"
)
_HOME_NOUN = re.compile(r"\b(?:CASA|VEREDA|URBANIZACION|URB|QUINTA)\b")
_OFFICE_LINE = re.compile(r"\b(?:NIVEL|LOCAL)\b|C\.C\.")
_ADDR_NOISE = {
    "ENTRE", "NIVEL", "LOCAL", "SECTOR", "CALLE", "CALLES", "AVENIDA", "AVDA",
    "ESTADO", "PISO", "TORRE", "DESDE", "HASTA", "ZONA", "URBANIZACION",
}
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
    letterhead_fields: set[str] = field(default_factory=set)

    @property
    def rejected_letterhead(self) -> bool:
        return bool(self.letterhead_fields)


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


def _year_from_two(yy: int, today: dt.date) -> int:
    """72 on a birth line is 1972; 24 on the same line is 2024."""
    return 2000 + yy if yy <= (today.year % 100) else 1900 + yy


def _month_token(token: str) -> int | None:
    token = token.rstrip(".")
    if token in _MONTHS:
        return _MONTHS[token]
    return _MONTH_ABBR.get(token[:3])


def _keep_date(found: list[dt.date], value: dt.date | None, today: dt.date | None) -> None:
    if value and plausible_dob(value, today=today) and value not in found:
        found.append(value)


def parse_dates(fragment: str, *, today: dt.date | None = None) -> list[dt.date]:
    found: list[dt.date] = []
    today = today or dt.date.today()
    for match in _DATE_NUMERIC.finditer(fragment):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        _keep_date(found, _try_date(year, month, day), today)
    for match in _DATE_SHORT.finditer(fragment):
        day, month = int(match.group(1)), int(match.group(2))
        year = _year_from_two(int(match.group(3)), today)
        _keep_date(found, _try_date(year, month, day), today)
    for match in _DATE_LONG.finditer(fragment):
        month = _MONTHS.get(match.group(2))
        if not month:
            continue
        _keep_date(found, _try_date(int(match.group(3)), month, int(match.group(1))), today)
    for match in _DATE_ABBR.finditer(fragment):
        month = _month_token(match.group(2))
        if not month:
            continue
        _keep_date(found, _try_date(int(match.group(3)), month, int(match.group(1))), today)
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
    """Venezuelan numbers, including 0414-728 37 61 and 0412 - 2353151."""
    found: list[str] = []
    for chunk in _PHONE_SPLIT.split(fold(text or "")):
        digits = re.sub(r"\D", "", chunk)
        start = 0
        while start + 10 <= len(digits):
            number = None
            consumed = 0
            for size in (12, 11, 10):
                if start + size > len(digits):
                    continue
                number = canonical_phone(digits[start : start + size])
                if number:
                    consumed = size
                    break
            if number and consumed:
                if number not in found:
                    found.append(number)
                start += consumed
            else:
                start += 1
    return found


def is_clinic_address(value: str | None) -> bool:
    """True when the line names a clinic, hospital, or insurer."""
    return bool(_CLINIC_ADDR.search(fold(value or "")))


def looks_like_home(value: str | None) -> bool:
    """A home line names a street. Headings, exam text, and office floors do not."""
    folded = fold(value or "")
    if not folded or is_clinic_address(folded) or _NOT_HOME.search(folded):
        return False
    if _OFFICE_LINE.search(folded) and not _HOME_NOUN.search(folded):
        return False
    return bool(_STREET_TOKEN.search(folded))


def address_signature(value: str | None) -> str:
    """Stable key for an address that shows up on many invoices (an office)."""
    words = [word for word in re.findall(r"[A-Z]{5,}", fold(value or "")) if word not in _ADDR_NOISE]
    if len(words) < 2:
        return ""
    return " ".join(sorted(set(words))[:5])


def repeated_address_signatures(
    records: list[tuple[str, str, str]],
    *,
    min_invoices: int = 8,
    min_people: int = 3,
) -> set[str]:
    """Signatures seen on many invoices and many titulares are letterhead, not a home."""
    invoices: dict[str, set[str]] = {}
    people: dict[str, set[str]] = {}
    for value, invoice_id, person_id in records:
        key = address_signature(value)
        if not key:
            continue
        invoices.setdefault(key, set()).add(invoice_id)
        people.setdefault(key, set()).add(person_id)
    return {
        key
        for key, seen in invoices.items()
        if len(seen) >= min_invoices and len(people.get(key, ())) >= min_people
    }


def clean_address(value: str | None, *, min_len: int = 8) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip(" .,:-|")
    if len(text) < min_len:
        return None
    text = text[:180]
    if is_clinic_address(text):
        return None
    return text


def _street_numbers(folded: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for match in _STREET_NUM.finditer(folded):
        token = _STREET_ALIAS.get(match.group(1), match.group(1))
        found.setdefault(token, set()).add(match.group(2))
    return found


def same_address(left: str, right: str) -> bool:
    a, b = fold(left), fold(right)
    if a == b:
        return True
    if len(a) >= 12 and len(b) >= 12 and (a in b or b in a):
        return True
    left_numbers, right_numbers = _street_numbers(a), _street_numbers(b)
    if not left_numbers or not right_numbers:
        return False
    shared = False
    for token, numbers in left_numbers.items():
        other = right_numbers.get(token)
        if not other:
            continue
        if numbers.isdisjoint(other):
            return False
        shared = True
    return shared


def select_address_hits(hits: list, stored: object = None) -> list | None:
    """Keep labeled addresses. A street line counts only when it matches one.

    None means the only hits are street lines that disagree, so nothing is written.
    """
    labeled = [hit for hit in hits if getattr(hit, "rule_id", None) != "street_line"]
    streets = [hit for hit in hits if getattr(hit, "rule_id", None) == "street_line"]

    def agrees(left: object, right: object) -> bool:
        return same_address(str(left), str(right))

    if stored:
        kept = [
            hit
            for hit in streets
            if agrees(stored, hit.value) or any(agrees(hit.value, lab.value) for lab in labeled)
        ]
        return labeled + kept
    if labeled:
        kept = [hit for hit in streets if any(agrees(hit.value, lab.value) for lab in labeled)]
        return labeled + kept
    groups: list[list] = []
    for hit in streets:
        placed = False
        for group in groups:
            if agrees(group[0].value, hit.value):
                group.append(hit)
                placed = True
                break
        if not placed:
            groups.append([hit])
    if len(groups) != 1:
        return None
    return streets


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
            _add_labeled_address(result, folded, match.end(), "acta_domicilio", 0.75)
            if any(c.rule_id == "acta_domicilio" for c in result.candidates):
                break
        _add_street_lines(result, folded)
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
            result.letterhead_fields.add("phone")
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
        _add_labeled_address(
            result,
            folded,
            match.end(),
            "form_address",
            0.7,
            ci=_nearest_ci(folded, match.start()),
            name=_name_around(folded, match.start()),
        )
    _add_street_lines(result, folded)
    return result


def _add_labeled_address(
    result: PageExtract,
    folded: str,
    pos: int,
    rule_id: str,
    confidence: float,
    *,
    ci: str | None = None,
    name: str | None = None,
) -> None:
    raw = _address_slice(folded, pos)
    if is_clinic_address(raw):
        result.letterhead_fields.add("address")
        return
    address = clean_address(raw)
    if not address or not looks_like_home(address):
        return
    result.candidates.append(Candidate("address", address, rule_id, confidence, block_ci=ci, block_name=name))


def _add_street_lines(result: PageExtract, folded: str) -> None:
    """Home lines that never say DIRECCION. Form and acta pages only."""
    for line in re.split(r"[\r\n]+", folded):
        if _ADDR_LABEL.search(line) or _NOT_HOME.search(line):
            continue
        if is_clinic_address(line):
            if _STREET_TOKEN.search(line):
                result.letterhead_fields.add("address")
            continue
        tokens = {match.group(0).rstrip(".").rstrip() for match in _STREET_TOKEN.finditer(line)}
        tokens = {_STREET_ALIAS.get(token, token) for token in tokens}
        if not tokens:
            continue
        if not re.search(
            r"\b(?:CASA|VEREDA|URBANIZACION|URB|QUINTA)\.?\s+(?:S\s*/\s*N|SIN|N[°º*]?|NUMERO)?\s*[A-Z0-9]",
            line,
        ):
            continue
        if len(tokens) < 2 and not re.search(r"\d", line):
            continue
        address = clean_address(line)
        if not address or not looks_like_home(address):
            continue
        if any(c.field == "address" and same_address(str(c.value), address) for c in result.candidates):
            continue
        result.candidates.append(Candidate("address", address, "street_line", 0.55))
        result.cues.add("address")


def _sole_titular(people: list[PersonOnInvoice]) -> str | None:
    titulares: list[str] = []
    for person in people:
        if person.role == "titular" and person.person_id not in titulares:
            titulares.append(person.person_id)
    return titulares[0] if len(titulares) == 1 else None


def _address_slice(folded: str, pos: int) -> str:
    window = folded[pos : pos + 160]
    window = re.split(
        r"\b(?:TELEFONO|TELF|CEDULA|C\.I|FECHA|PARENTESCO|CORREO|EMAIL|"
        r"DATOS|MEDICO|MOTIVO|DIAGNOSTICO|REFERENCIA)\b",
        window,
    )[0]
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
        if len(hits) > 1 or candidate.rule_id not in {"form_address", "street_line"}:
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
        titular_id = _sole_titular(people)
        if titular_id:
            return titular_id, "bound"
        return None, "ambiguous"
    if candidate.rule_id in {"form_address", "street_line"}:
        titular_id = _sole_titular(people)
        if titular_id:
            return titular_id, "bound"
        return None, "ambiguous"
    if candidate.rule_id == "cedula_dob" and sole_dob and hint_person_id:
        return hint_person_id, "bound"
    return None, "ambiguous"
