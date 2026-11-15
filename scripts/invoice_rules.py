"""Explainable file-level rules for fiscal invoices in Avila-backup.

Classification uses the relative path only. It does not open files.
A named FACT / FAC / FACTURA document is an invoice packet. Pages inside
that packet are separated later. Clinical files that merely mention an
invoice number are supporting documents, not invoices.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict

INVOICE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".pptx", ".potx", ".ppt"}
SKIP_EXTENSIONS = {".lnk", ".ini", ".tmp", ".rar"}

# Longer keys first so SENIAT wins over SENIA and PREVISORA over PREVISA.
ACCOUNTS = (
    ("CEMENTO", "Cemento Andino"),
    ("PIRAMIDE", "Piramide"),
    ("PIRAMIR", "Piramide"),
    ("HISPANA", "Hispana"),
    ("CONTITUCION", "Constitucion"),
    ("CONSTITUCION", "Constitucion"),
    ("ALTAMIRA", "Altamira"),
    ("LATITUD", "Latitud"),
    ("LATITUC", "Latitud"),
    ("PREVISORA", "La Previsora"),
    ("PREVISOR", "La Previsora"),
    ("PREVISA", "La Previsora"),
    ("SENIAT", "SENIAT"),
    ("VENEZUELA", "Seguros Venezuela"),
    ("VENEZUEL", "Seguros Venezuela"),
    ("MIRANDA", "Seguros Miranda"),
    ("FASMEE", "FASMEE"),
    ("FASME", "FASMEE"),
    ("CORPOELEC", "CORPOELEC"),
    ("CORPORACION", "Corporacion"),
    ("PUEBLO SOBERANO", "Pueblo Soberano"),
    ("BICENTENARIO", "Bicentenario"),
    ("CUIDAMED", "Cuidamed"),
    ("SAREN", "SAREN"),
    ("SAREM", "SAREN"),
    ("CANTV", "CANTV"),
    ("ALMIRA", "Altamira"),
    ("SENIA", "SENIAT"),
)

MONTHS = (
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "SEPT",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)

# Clinical and register roles win over a FACT number sitting later in the name.
SUPPORTING_ROLES = (
    ("egreso", re.compile(r"(?:^|[^A-Z])(?:EGRESO|ENGRESO)(?:[^A-Z]|$)")),
    ("ingreso", re.compile(r"(?:^|[^A-Z])INGRESO(?:[^A-Z]|$)")),
    ("carta_aval", re.compile(r"CARTA\s*AVAL")),
    ("presupuesto", re.compile(r"(?:^|[^A-Z])(?:PRESUPUESTO|PROFORMA)(?:[^A-Z]|$)")),
)
REGISTER_ROLES = (
    ("baremo", re.compile(r"(?:^|[^A-Z])BAREMOS?(?:[^A-Z]|$)")),
    ("sabana", re.compile(r"(?:^|[^A-Z])SABANAS?(?:[^A-Z]|$)")),
    ("relacion", re.compile(r"(?:^|[^A-Z])RELACION(?:[^A-Z]|$)")),
    ("cintillo", re.compile(r"(?:^|[^A-Z])CINTILLO(?:[^A-Z]|$)")),
)

RANGE_RE = re.compile(r"FACT(?:URA)?\s*(\d{3,6})\s*[-–—]\s*(\d{3,6})")
ANY_RANGE_RE = re.compile(r"(\d{3,6})\s*[-–—]\s*(\d{3,6})")
FACT_NUM_RE = re.compile(r"(?:^|[^A-Z])FACT(?:URA)?\s*(\d{3,6})\b")
FAC_NUM_RE = re.compile(r"(?:^|[^A-Z])FAC\s*(\d{3,6})\b")
FACTURA_WORD_RE = re.compile(r"(?:^|[^A-Z])FACTURA(?:[^A-Z]|$)")
FACT_WORD_RE = re.compile(r"(?:^|[^A-Z])FACT(?:[^A-Z]|$)")
YEAR_RE = re.compile(r"(?<!\d)(202[3-7])(?!\d)")
LOTE_RE = re.compile(r"LOTE\s*([0-9]{1,2}|VIII|VII|VI|IX|IV|III|II|I)\b")
PARTE_RE = re.compile(r"PARTE\s*([0-9]{1,2})")


@dataclass
class Classification:
    label: str
    rule_id: str
    confidence: str
    invoice_number: str
    invoice_numbers: str
    invoice_range: str
    related_invoice_number: str
    account: str
    account_labels: str
    account_raw: str
    month: str
    year: str
    lote: str
    parte: str
    lot: str
    workflow: str
    channel: str
    duplicate_group: str

    def as_row(self) -> dict:
        return asdict(self)


def fold(text: str) -> str:
    """Uppercase and strip accents so Escáner and ESCANER match."""
    text = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.upper()


def _stem(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return fold(base)


def _extension(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return "." + base.rsplit(".", 1)[1].lower()


def _is_year_span(start: int, end: int) -> bool:
    return 2020 <= start <= 2030 and 2020 <= end <= 2030


def fact_tokens(text: str) -> tuple[list[tuple[int, int]], list[int]]:
    """Return (ranges, singles) from a folder or file title.

    Numbers that are the endpoints of a range are not also returned as singles.
    A second span written as '16979-16992' after a FACT range is kept.
    Year spans such as 2024-2025 are not invoice ranges.
    """
    folded = fold(text)
    ranges = [(int(a), int(b)) for a, b in RANGE_RE.findall(folded)]
    if "FACT" in folded:
        for a, b in ANY_RANGE_RE.findall(folded):
            pair = (int(a), int(b))
            if pair not in ranges and not _is_year_span(*pair):
                ranges.append(pair)
    masked = folded
    spans = []
    for match in ANY_RANGE_RE.finditer(folded):
        if _is_year_span(int(match.group(1)), int(match.group(2))):
            continue
        spans.append((match.start(), match.end()))
    for start, end in reversed(spans):
        masked = masked[:start] + (" " * (end - start)) + masked[end:]
    singles = [int(n) for n in FACT_NUM_RE.findall(masked)]
    singles += [int(n) for n in FAC_NUM_RE.findall(masked)]
    return ranges, singles


def _format_tokens(ranges: list[tuple[int, int]], singles: list[int]) -> str:
    parts = [f"{a}-{b}" for a, b in ranges]
    parts += [str(n) for n in singles]
    # Preserve order, drop duplicates.
    seen = set()
    out = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            out.append(part)
    return ";".join(out)


def _path_parts(relative_path: str) -> list[str]:
    return [part for part in relative_path.replace("\\", "/").split("/") if part and part != "."]


def _ancestor_tokens(parts: list[str]) -> tuple[list[tuple[int, int]], list[int], str]:
    """Collect FACT numbers from every directory above the file."""
    ranges: list[tuple[int, int]] = []
    singles: list[int] = []
    raw_hits: list[str] = []
    for part in parts[:-1]:
        found_ranges, found_singles = fact_tokens(part)
        if found_ranges or found_singles:
            raw_hits.append(part)
        ranges.extend(found_ranges)
        singles.extend(found_singles)
    return ranges, singles, " | ".join(raw_hits)


def _accounts(relative_path: str, parts: list[str]) -> tuple[str, str, str]:
    folded_parts = [fold(part) for part in parts[:-1]]
    folded_path = " / ".join(folded_parts)
    labels: list[str] = []
    raw_title = parts[-2] if len(parts) > 1 else ""
    for key, label in ACCOUNTS:
        if key in folded_path and label not in labels:
            labels.append(label)
    if not labels:
        return "", "", raw_title
    if len(labels) == 1:
        return labels[0], labels[0], raw_title
    return "mixed", ";".join(labels), raw_title


def _month(folded_path: str) -> str:
    for name in MONTHS:
        if re.search(rf"(?:^|[^A-Z]){name}(?:[^A-Z]|$)", folded_path):
            if name == "SEPT":
                return "SEPTIEMBRE"
            return name
    return ""


def _workflow(parts: list[str]) -> str:
    state = ""
    for part in parts[:-1]:
        folded = fold(part)
        if "PROCES" in folded:
            state = "procesadas"
        elif re.search(r"(?:^|[^A-Z])LISTAS(?:[^A-Z]|$)", folded):
            state = "listas"
        elif "DIGITAL" in folded:
            state = "digitalizaciones"
    return state


def _lot(month: str, year: str, lote: str, parte: str) -> str:
    bits = []
    if month:
        bits.append(month.title())
    if year:
        bits.append(year)
    if lote:
        bits.append(f"lote {lote}")
    if parte:
        bits.append(f"parte {parte}")
    return " ".join(bits)


def _is_unnamed_scan(stem: str) -> bool:
    if re.match(r"IMG(?:[\s_\-]|\d)", stem):
        return True
    if stem.startswith("ESCANER") or stem.startswith("ESCAN"):
        return True
    if stem.startswith("SCANNER") or stem.startswith("SCANER") or stem.startswith("SCAN_") or stem.startswith("SCAN "):
        return True
    if stem.startswith("SCAR "):
        return True
    return False


def _is_template(stem: str, ext: str) -> bool:
    if "FORMATO" in stem and "FACTURA" in stem:
        return True
    if "INSUMO" in stem and ("HOSPITAL" in stem or "FORMATO" in stem):
        return True
    if ext in {".xlsx", ".xls"} and "FACTURA" in stem:
        return True
    return False


def _first_role(stem: str):
    for name, pattern in SUPPORTING_ROLES:
        if pattern.search(stem):
            return "supporting", name
    for name, pattern in REGISTER_ROLES:
        if pattern.search(stem):
            return "not_invoice", name
    return "", ""


def _filename_numbers(stem: str) -> tuple[str, str, list[int]]:
    """Return (kind, numbers_csv, number_list).

    kind is 'fact', 'fac', 'word', or ''.
    """
    ranges, singles = fact_tokens(stem)
    numbers = []
    for start, end in ranges:
        numbers.extend((start, end))
    numbers.extend(singles)
    # Keep first-seen order.
    ordered = []
    for number in numbers:
        if number not in ordered:
            ordered.append(number)
    if ordered and FACT_NUM_RE.search(stem):
        kind = "fact"
    elif ordered and FAC_NUM_RE.search(stem):
        kind = "fac"
    elif FACTURA_WORD_RE.search(stem) or FACT_WORD_RE.search(stem):
        kind = "word"
    else:
        kind = ""
    return kind, ";".join(str(n) for n in ordered), ordered


def _blank(**overrides) -> Classification:
    data = dict(
        label="not_invoice",
        rule_id="default_not_invoice",
        confidence="",
        invoice_number="",
        invoice_numbers="",
        invoice_range="",
        related_invoice_number="",
        account="",
        account_labels="",
        account_raw="",
        month="",
        year="",
        lote="",
        parte="",
        lot="",
        workflow="",
        channel="",
        duplicate_group="",
    )
    data.update(overrides)
    return Classification(**data)


def classify(relative_path: str) -> Classification:
    """Classify one backup-relative path. Directories are not accepted."""
    parts = _path_parts(relative_path)
    if not parts:
        return _blank(rule_id="empty_path")
    filename = parts[-1]
    ext = _extension(filename)
    stem = _stem(filename)
    channel = parts[0] if len(parts) > 1 else "(root)"
    account, account_labels, account_raw = _accounts(relative_path, parts)
    folded_dirs = fold(" / ".join(parts[:-1]))
    context = folded_dirs + " / " + stem
    month = _month(context)
    year_match = YEAR_RE.search(context)
    year = year_match.group(1) if year_match else ""
    lote_match = LOTE_RE.search(context)
    lote = lote_match.group(1) if lote_match else ""
    parte_match = PARTE_RE.search(context)
    parte = parte_match.group(1) if parte_match else ""
    workflow = _workflow(parts)
    lot = _lot(month, year, lote, parte)
    ranges, singles, _raw = _ancestor_tokens(parts)
    invoice_range = _format_tokens(ranges, singles)
    kind, numbers_csv, numbers = _filename_numbers(stem)

    common = dict(
        account=account,
        account_labels=account_labels,
        account_raw=account_raw,
        month=month,
        year=year,
        lote=lote,
        parte=parte,
        lot=lot,
        workflow=workflow,
        channel=channel,
        invoice_range=invoice_range,
    )

    folded_name = fold(filename)
    if filename.startswith(".") or filename.startswith("~$") or ext in SKIP_EXTENSIONS:
        return _blank(rule_id="skipped_sidecar", **common)

    if _is_template(stem, ext):
        return _blank(label="template", rule_id="template_not_issued", confidence="", **common)

    role_label, role_name = _first_role(stem)
    if role_name:
        related = numbers_csv
        rule = f"role_{role_name}"
        return _blank(
            label=role_label,
            rule_id=rule,
            related_invoice_number=related,
            invoice_numbers=numbers_csv,
            **common,
        )

    folder_singles = list(singles)
    for start, end in ranges:
        if start == end:
            folder_singles.append(start)
    unique_folder = []
    for number in folder_singles:
        if number not in unique_folder:
            unique_folder.append(number)

    def with_number(chosen: str, number_list: list[int]) -> str:
        if chosen:
            return f"fact-{chosen}"
        return ""

    if kind and ext in INVOICE_EXTENSIONS:
        if len(numbers) == 1:
            chosen = str(numbers[0])
            confidence = "high" if kind == "fact" else "medium"
            rule = "named_fact_number" if kind == "fact" else "named_fac_number"
        elif len(numbers) > 1:
            chosen = ""
            confidence = "medium"
            rule = "named_fact_multi"
        else:
            chosen = str(unique_folder[0]) if len(unique_folder) == 1 and not ranges else ""
            confidence = "medium"
            rule = "named_fact_word" if not chosen else "named_fact_word_folder_number"
            if ranges and not chosen:
                rule = "named_fact_word_folder_range"
        return _blank(
            label="invoice_packet",
            rule_id=rule,
            confidence=confidence,
            invoice_number=chosen,
            invoice_numbers=numbers_csv or chosen,
            duplicate_group=with_number(chosen, numbers),
            **common,
        )

    if kind and ext not in INVOICE_EXTENSIONS:
        return _blank(
            rule_id="named_fact_unsupported_extension",
            invoice_numbers=numbers_csv,
            related_invoice_number=numbers_csv if len(numbers) == 1 else "",
            **common,
        )

    folder_has_fact = bool(ranges or singles)
    if stem.startswith("GPSPDF") and folder_has_fact:
        return _blank(
            label="needs_page_check",
            rule_id="gpspdf_bundle",
            confidence="low",
            **common,
        )

    if _is_unnamed_scan(stem) and folder_has_fact:
        return _blank(
            label="needs_page_check",
            rule_id="scan_in_fact_batch",
            confidence="low",
            **common,
        )

    if _is_unnamed_scan(stem):
        return _blank(rule_id="scan_outside_invoice", **common)

    return _blank(**common)
