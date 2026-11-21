"""Read doctors, especialidad terms, patient block, and diagnosis from one OCR page.

Pure functions, no database. Every result carries the rule that produced it.
Especialidad strings are only read from title, label, doctor-stamp, and
referral lines; exam prose ("EXAMEN NEUROLOGICO") is never scanned.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from document_types import extract_all_cedulas
from especialidad_normalize import (
    ADJECTIVE_CONTEXTS,
    SPECIALTY_KINDS,
    Match,
    best_specialty,
    default_catalog,
    degree_of,
    normalize_text,
)
from invoice_rules import fold
from person_name_gate import sanitize_person_name

EXTRACTOR_VERSION = "clinical-1"

GPS_RIF_DIGITS = "41029281"
REPORT_KINDS = {
    "informe_medico": "informe",
    "orden_servicio": "orden",
    "laboratorio": "laboratorio",
    "imagenologia": "imagen",
}

_MPPS = re.compile(r"M\s*\.?\s*P\s*\.?\s*P\s*\.?\s*S\s*\.?\s*(?:N\s*[°º.]?\s*)?[:;.\-]?\s*(\d[\d.\s]{2,9}\d)")
_MPPS_CUE = re.compile(r"M\s*\.?\s*P\s*\.?\s*P\s*\.?\s*S|\bA\s*PPS\b")
_COLEGIO = re.compile(r"\b(C\s*\.?\s*M\s*\.?\s*[A-Z]?\s*\.?|CDMD|COMEM)\s*[:;.]\s*(\d[\d.]{2,7})")
_DOCTOR_RIF = re.compile(r"\bRIF\s*[:.]?\s*([VE])\s*-?\s*(\d{6,9})\s*-?\s*(\d)?")
_TITLE = re.compile(r"^[^A-Z0-9]*(DRA|DR|ORA|OR)\b\s*[\.,:;]?\s*(.+)$")
_LABEL_ROLE = re.compile(
    r"(MEDICO\s+TRATANTE|MEDICO\s+SOLICITANTE|SOLICITADO\s+POR|REFERIDO\s+POR|MEDICO\s+REFERENTE)\s*[:;.]?\s*"
    r"(?:(DRA|DR|ORA|OR)\b\s*[\.,:;]?\s*)?(.*)$"
)
_NAME_CUT = re.compile(
    r"\s*(?:\||MPPS|M\.P\.P|\bC\.?\s*M\b|\bCMT\b|\bC\.?\s*I\b|\bCEDULA|\bRIF\b|\bMEDIC[OA]\b|\bESPECIALISTA|"
    r"\bTLF|\bTELF|\bTELEFONO|\bCEL\b|\bFIRMA|\bSELLO|\d).*$"
)
_NOT_NAME_TOKENS = frozenset(
    {
        "INFORME", "PACIENTE", "DIAGNOSTICO", "MEDICO", "MEDICA", "ESPECIALISTA", "CLINICA", "CENTRO",
        "HOSPITAL", "SERVICIO", "UNIDAD", "CONSULTA", "FECHA", "EDAD", "SEXO", "PLAN", "FIRMA", "SELLO",
        "ATENTAMENTE", "GESTION", "PROFESIONAL", "SALUD", "GPS", "INTERNISTA", "CIRUJANO",
        # Letterhead and address words that follow a name on the same OCR line.
        "SECTOR", "URB", "URBANIZACION", "AV", "AVENIDA", "CALLE", "CARRERA", "EDIF", "EDIFICIO", "TORRE",
        "PISO", "LOCAL", "CONSULTORIO", "SEGUROS", "APS", "POR", "ESPECIALIDADES", "TELEFONO", "EMAIL",
    }
)
_NAME_CONNECTORS = frozenset({"DE", "DEL", "LA", "LAS", "LOS", "Y"})
_PATIENT = re.compile(
    r"(?:NOMBRE\s+DEL\s+PACIENTE|NOMBRES?\s+Y\s+APELLIDOS?|APELLIDOS?\s+Y\s+NOMBRES?|NOMBRE\s+APELLIDO|"
    r"PACIENTE|NOMBRE)\s*([:;])?\s*(.*)$"
)
_PROSE_AFTER_PACIENTE = frozenset(
    {"MASCULINO", "FEMENINO", "DE", "QUE", "CON", "EN", "QUIEN", "ACUDE", "REFIERE", "PRESENTA", "CONSULTA", "EL", "LA"}
)
_PATIENT_CUT = re.compile(
    r"\s*(?:\bC\s*[.,]?\s*[IL1]\b|\bCI\b|\bC\s*\.\s*\.|\bCEDULA|\bFECHA|\bEDAD|\bSEXO|\bF\.?\s*N\b|\bHC\b|\bH\.C|"
    r"\bINFORME\b|\(|\d).*$"
)
_EDAD = re.compile(r"\bEDAD\s*[:;]?\s*(\d{1,3})\b")
_DATE = re.compile(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2,4})")
_CONSULT_DATE = re.compile(r"FECHA\s*(?:DE\s+(?:LA\s+)?(?:CONSULTA|ATENCION|EVALUACION|INFORME|EMISION))?\s*[:;]")
_BIRTH = re.compile(r"NACIMIENTO|\bF\s*\.?\s*N\s*\.?\s*[:;]")
_DIAGNOSIS = re.compile(
    r"^[^A-Z]*(?:\d+\s*[.\-)]\s*)?(IMPRESION(?:ES)?\s+DIAGNOSTICAS?|DIAGNOSTICOS?(?:\s+DE\s+INGRESO|\s+DE\s+EGRESO)?|IDX|DX)"
    r"\b\s*[:;.\-]?\s*(.*)$"
)
_DIAGNOSIS_STOP = re.compile(
    r"^[^A-Z]*(PLAN|CONDUCTA|TRATAMIENTO|INDICACIONES|RECOMENDACIONES|RECOMENDACION|SE\s+INDICA|EXAMEN|"
    r"REFERENCIA|ATENTAMENTE|DRA?\b|ORA?\.|MPPS|M\.P\.P|FIRMA|CMT|MEDICO\s+\w+|EVOLUCION|PRONOSTICO)\b"
)
_REPORT_TITLE = re.compile(r"\bINFORME\b|\bSERVICIO\s+DE\b|\bUNIDAD\s+DE\b|\bESTUDIO\s+DE\b|\bREPORTE\s+DE\b")
_INFORME_TITLE = re.compile(r"\bINFORME\s+M?\s*E?DICO\b|\bINFORME\s+DE\b")
_LABEL = re.compile(r"\bESPECIALIDAD\s*[:;]?\s*(.*)$")
_REFERRAL = re.compile(
    r"\b(?:REFERENCIA|REFERIDO|REFIERE|SE\s+REFIERE|INTERCONSULTA|EVALUACION)\s+(?:A|AL|CON|POR|PARA)\s+(.*)$"
)


@dataclass
class Doctor:
    title: str | None
    name: str | None
    name_folded: str
    mpps: str | None
    colegio: str | None
    rif: str | None
    zone: str
    role: str
    rule_id: str
    line_index: int
    title_lines: list[str] = field(default_factory=list)
    especialidad: str | None = None
    especialidad_method: str | None = None
    degree: str | None = None
    degree_university: str | None = None


def fold_name(name: str | None) -> str:
    return " ".join(fold(name or "").split())


def _zone(index: int, total: int) -> str:
    if total <= 0:
        return "body"
    ratio = index / total
    if ratio < 0.25:
        return "header"
    if ratio >= 0.7:
        return "footer"
    return "body"


def _clean_doctor_name(raw: str) -> str | None:
    text = _NAME_CUT.sub("", raw)
    text = re.sub(r"[^A-ZÑ\s.']", " ", text)
    tokens = [t.strip(".'") for t in text.split()]
    while tokens and tokens[0] in {"DR", "DRA"}:
        tokens = tokens[1:]
    if any(t in _NOT_NAME_TOKENS for t in tokens):
        cut = next(i for i, t in enumerate(tokens) if t in _NOT_NAME_TOKENS)
        tokens = tokens[:cut]
    tokens = [t for t in tokens if len(t) > 2 or t in _NAME_CONNECTORS]
    while tokens and tokens[-1] in _NAME_CONNECTORS:
        tokens = tokens[:-1]
    name = sanitize_person_name(" ".join(tokens[:6]))
    if not name or sum(len(t) for t in name.split()) < 6:
        return None
    return name.title()


def _license_near(lines: list[str], index: int, span: int = 4) -> tuple[str | None, str | None, int | None]:
    """MPPS and colegio numbers within ``span`` lines below ``index`` (stamp block)."""
    for offset in range(0, span + 1):
        i = index + offset
        if i >= len(lines):
            break
        mpps = _MPPS.search(lines[i])
        if mpps or _MPPS_CUE.search(lines[i]):
            colegio = _COLEGIO.search(lines[i]) or (_COLEGIO.search(lines[i - 1]) if i > index else None)
            return (
                _digits(mpps.group(1)) if mpps else None,
                _digits(colegio.group(2)) if colegio else None,
                i,
            )
    return None, None, None


def _digits(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if 3 <= len(digits) <= 8 else None


def _doctor_rif(lines: list[str], start: int, end: int) -> str | None:
    for i in range(max(0, start), min(len(lines), end + 1)):
        match = _DOCTOR_RIF.search(lines[i])
        if match and match.group(2) != GPS_RIF_DIGITS:
            return f"{match.group(1)}-{match.group(2)}{match.group(3) or ''}"
    return None


def parse_doctors(lines: list[str]) -> list[Doctor]:
    """Doctors named on the page: labeled roles, DR/DRA stamps, and bare-name stamps."""
    total = len(lines)
    doctors: list[Doctor] = []
    used: set[int] = set()

    for index, line in enumerate(lines):
        label = _LABEL_ROLE.search(line)
        if not label:
            continue
        rest = label.group(3) or (lines[index + 1] if index + 1 < total else "")
        name = _clean_doctor_name(rest)
        if not name:
            continue
        role = "tratante" if "TRATANTE" in label.group(1) else "solicitante"
        mpps, colegio, _ = _license_near(lines, index, 2)
        doctors.append(
            Doctor(
                title=_title(label.group(2)), name=name, name_folded=fold_name(name), mpps=mpps, colegio=colegio,
                rif=None, zone=_zone(index, total), role=role, rule_id=f"label_{role}", line_index=index,
            )
        )
        used.add(index)

    for index, line in enumerate(lines):
        if index in used:
            continue
        match = _TITLE.match(line)
        if not match:
            continue
        prefix = match.group(1)
        mpps, colegio, license_line = _license_near(lines, index)
        if prefix.startswith("O") and license_line is None:
            continue
        name = _clean_doctor_name(match.group(2))
        if not name:
            continue
        zone = _zone(index, total)
        end = license_line if license_line is not None else min(index + 2, total - 1)
        title_lines = [lines[i] for i in range(index + 1, end + 1) if i < total]
        if license_line is None and index + 1 < total:
            title_lines = [lines[index + 1]]
        # An unlicensed DR line inside the narrative names someone, not the author.
        role = "referido" if license_line is None and zone == "body" else "firmante"
        doctors.append(
            Doctor(
                title=_title(prefix), name=name, name_folded=fold_name(name), mpps=mpps, colegio=colegio,
                rif=_doctor_rif(lines, index, end + 1), zone=zone, role=role,
                rule_id="stamp_or" if prefix.startswith("O") else ("stamp_dr" if license_line is not None else "dr_line"),
                line_index=index, title_lines=title_lines,
            )
        )
        used.add(index)

    named_licenses = {d.mpps for d in doctors if d.mpps}
    for index, line in enumerate(lines):
        mpps = _MPPS.search(line)
        if not mpps:
            continue
        number = _digits(mpps.group(1))
        if not number or number in named_licenses:
            continue
        colegio = _COLEGIO.search(line)
        # Bare stamp: NAME / MEDICO <title> / MPPS. The name is the first usable
        # line above the license that is not itself a title line.
        name = None
        name_line = None
        title_lines: list[str] = []
        for back in range(1, 4):
            i = index - back
            if i < 0 or i in used:
                break
            matches = normalize_text(lines[i], "doctor_title")
            if degree_of(matches) or best_specialty(matches) or lines[i].startswith("MEDICO"):
                title_lines.insert(0, lines[i])
                continue
            name = _clean_doctor_name(lines[i])
            name_line = i
            break
        doctors.append(
            Doctor(
                title=None, name=name, name_folded=fold_name(name), mpps=number,
                colegio=_digits(colegio.group(2)) if colegio else None,
                rif=_doctor_rif(lines, index - 3, index + 1), zone=_zone(index, total), role="firmante",
                rule_id="stamp_bare_name" if name else "stamp_license_only",
                line_index=name_line if name_line is not None else index, title_lines=title_lines,
            )
        )
        named_licenses.add(number)

    for doctor in doctors:
        matches: list[Match] = []
        for title_line in doctor.title_lines:
            matches.extend(normalize_text(title_line, "doctor_title"))
        specialty = best_specialty(matches)
        if specialty:
            doctor.especialidad = specialty.especialidad
            doctor.especialidad_method = specialty.method
        degree = degree_of(matches)
        if degree:
            doctor.degree = degree.degree
            doctor.degree_university = degree.university
    return doctors


def _title(prefix: str | None) -> str | None:
    if not prefix:
        return None
    return "dra" if prefix.endswith("A") else "dr"


def especialidad_lines(lines: list[str], doctors: list[Doctor]) -> list[tuple[str, str]]:
    """(text, context) pairs eligible for especialidad normalization."""
    out: list[tuple[str, str]] = []
    head = max(8, int(len(lines) * 0.4))
    for index, line in enumerate(lines):
        label = _LABEL.search(line)
        if label:
            text = label.group(1).strip(" :;.-")
            if not text and index + 1 < len(lines):
                text = lines[index + 1]
            if text:
                out.append((text, "label"))
            continue
        referral = _REFERRAL.search(line)
        if referral:
            out.append((referral.group(1), "referral"))
            continue
        if index < head and _REPORT_TITLE.search(line) and not _PATIENT.search(line):
            out.append((line, "report_title"))
    for doctor in doctors:
        for title_line in doctor.title_lines:
            out.append((title_line, "doctor_title"))
    return out


def _clean_patient_name(raw: str) -> str | None:
    text = re.sub(r"^\s*M?E?DICO\b", "", raw)
    text = _PATIENT_CUT.sub("", text)
    text = re.sub(r"[^A-ZÑ\s]", " ", text)
    return sanitize_person_name(" ".join(text.split()))


def parse_patient(lines: list[str]) -> dict:
    """Name, cédula, age from the patient block near the top of the page."""
    head = max(10, int(len(lines) * 0.5))
    result: dict = {"name": None, "ci": None, "edad": None, "rule": None}
    for index, line in enumerate(lines[:head]):
        match = _PATIENT.search(line)
        if not match:
            continue
        colon, rest = match.group(1), match.group(2)
        first = (rest.split() or [""])[0]
        if not colon and first in _PROSE_AFTER_PACIENTE:
            continue
        name = _clean_patient_name(rest)
        if not name:
            continue
        window = " ".join(lines[index:index + 3])
        cis = [ci for ci in extract_all_cedulas(window) if not ci.startswith(GPS_RIF_DIGITS)]
        result.update(name=name.title(), ci=cis[0] if cis else None, rule="label_colon" if colon else "label_bare")
        break
    for line in lines[:head]:
        edad = _EDAD.search(line)
        if edad:
            result["edad"] = int(edad.group(1))
            break
    if result["ci"] is None:
        for line in lines[:head]:
            if re.search(r"\bC\s*[.,]?\s*[IL1]\b|CEDULA", line) and not re.search(r"\bRIF\b", line):
                cis = [ci for ci in extract_all_cedulas(line) if not ci.startswith(GPS_RIF_DIGITS)]
                if cis:
                    result["ci"] = cis[0]
                    break
    return result


def _to_date(day: str, month: str, year: str) -> date | None:
    y = int(year)
    if y < 100:
        y += 2000
    try:
        value = date(y, int(month), int(day))
    except ValueError:
        return None
    return value if 2015 <= value.year <= 2027 else None


def parse_encounter_date(lines: list[str]) -> str | None:
    head = max(12, int(len(lines) * 0.5))
    fallback = None
    for line in lines[:head]:
        for label in _CONSULT_DATE.finditer(line):
            before = line[max(0, label.start() - 4):label.start()]
            if "F." in before:
                continue
            tail = line[label.end():]
            if tail.lstrip().startswith("DE NACIMIENTO"):
                continue
            match = _DATE.search(tail[:20])
            if match:
                value = _to_date(*match.groups())
                if value:
                    return value.isoformat()
        if fallback is None and not _BIRTH.search(line):
            match = _DATE.search(line)
            if match:
                value = _to_date(*match.groups())
                if value:
                    fallback = value.isoformat()
    return fallback


def parse_diagnosis(raw_lines: list[str], lines: list[str]) -> str | None:
    """Diagnosis block in the page's own casing, at most ~600 characters."""
    for index, line in enumerate(lines):
        match = _DIAGNOSIS.match(line)
        if not match:
            continue
        parts: list[str] = []
        offset = match.start(2)
        first = raw_lines[index][offset:].strip(" :;.-|")
        if first:
            parts.append(first)
        for j in range(index + 1, min(index + 7, len(lines))):
            if _DIAGNOSIS_STOP.match(lines[j]):
                break
            parts.append(raw_lines[j].strip(" |"))
        text = " ".join(" ".join(parts).split())
        text = re.sub(r"[|_]{2,}", " ", text).strip(" :;.-")
        if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", text)) >= 4:
            return text[:600]
    return None


def text_fingerprint(text: str) -> str:
    letters = re.sub(r"[^A-Z]", "", fold(text or ""))
    return hashlib.sha256(letters.encode("ascii")).hexdigest()[:24]


def _match_dict(match: Match) -> dict:
    return {
        "context": match.context,
        "raw": match.raw,
        "l1": match.l1,
        "method": match.method,
        "distance": match.distance,
        "kind": match.kind,
        "term": match.term.term if match.term else None,
        "especialidad": match.especialidad,
        "procedimiento": match.procedimiento,
        "degree": match.degree,
        "university": match.university,
    }


def parse_page(text: str | None) -> dict:
    """Everything the clinical pipeline needs from one page."""
    raw_lines = [line for line in (text or "").splitlines() if line.strip()]
    lines = [fold(line) for line in raw_lines]
    doctors = parse_doctors(lines)
    matches: list[Match] = []
    for snippet, context in especialidad_lines(lines, doctors):
        matches.extend(normalize_text(snippet, context))
    head = max(8, int(len(lines) * 0.4))
    return {
        "has_title": any(_INFORME_TITLE.search(line) for line in lines[:head]),
        "doctors": [asdict(d) for d in doctors],
        "terms": [_match_dict(m) for m in matches],
        "patient": parse_patient(lines),
        "encounter_date": parse_encounter_date(lines),
        "diagnosis": parse_diagnosis(raw_lines, lines),
        "fingerprint": text_fingerprint(text or ""),
    }


def visit_specialty(terms: list[dict]) -> tuple[str | None, str | None]:
    """(especialidad code, source) from page terms by precedence; referrals excluded."""
    order = ("label", "doctor_title", "report_title")
    for context in order:
        picked = _best_from_dicts([t for t in terms if t["context"] == context])
        if picked:
            return picked, context
    return None, None


def _best_from_dicts(terms: list[dict]) -> str | None:
    catalog = default_catalog()
    codes = [
        t["especialidad"]
        for t in terms
        if t["kind"] in SPECIALTY_KINDS
        and t["especialidad"]
        and (t["kind"] != "adjective" or t["context"] in ADJECTIVE_CONTEXTS)
    ]
    if not codes:
        return None
    for code in codes:
        if any(catalog.is_descendant(code, other) for other in codes):
            return code
    return codes[0]


def referred_specialty(terms: list[dict]) -> str | None:
    return _best_from_dicts([dict(t, context="report_title") for t in terms if t["context"] == "referral"])


def page_procedure(terms: list[dict]) -> str | None:
    for term in terms:
        if term["kind"] == "procedure" and term["context"] in ("label", "report_title") and term["procedimiento"]:
            return term["procedimiento"]
    return None


def group_report_pages(pages: list[dict]) -> list[list[dict]]:
    """Merge consecutive pages of one report in the same file.

    ``pages`` are ordered by (source_file_id, page_index) and carry ``parsed``.
    A page continues the previous one when it has no report title and no
    patient block of its own.
    """
    groups: list[list[dict]] = []
    for page in pages:
        if groups:
            prev = groups[-1][-1]
            parsed = page["parsed"]
            same_file = prev["source_file_id"] == page["source_file_id"]
            adjacent = page["page_index"] == prev["page_index"] + 1
            continuation = not parsed["has_title"] and not parsed["patient"]["name"] and not parsed["patient"]["ci"]
            if same_file and adjacent and continuation and page["document_type"] == groups[-1][0]["document_type"]:
                groups[-1].append(page)
                continue
        groups.append([page])
    return groups


__all__ = [
    "EXTRACTOR_VERSION",
    "REPORT_KINDS",
    "Doctor",
    "fold_name",
    "group_report_pages",
    "page_procedure",
    "parse_diagnosis",
    "parse_doctors",
    "parse_encounter_date",
    "parse_page",
    "parse_patient",
    "referred_specialty",
    "text_fingerprint",
    "visit_specialty",
]
