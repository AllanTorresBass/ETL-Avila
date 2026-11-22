"""One request header, its study items, and the workbook rows that copy it.

The header stays ``avila.authorization_line``. A specialty on the same row is
one item. Following rows with no cédula and a study label are more items of
that request. Two lines are the same request when the person, date, amount,
diagnosis, and item labels match and only one filename carries an APS number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .canonical import fold_header
from .normalize import clean_name, row_dict, row_has_person_signal

ITEM_COLUMNS = {
    "ESPECIALIDAD MEDICA": "consulta",
    "ESTUDIO ESPECIAL": "estudio",
}

_SKIP_LABELS = {
    "TOTAL",
    "MONTO",
    "OBSERVACIONES",
    "ESPECIALIDAD MEDICA",
    "ESTUDIO ESPECIAL",
}

_APS_RE = re.compile(r"(?:^|[^A-Za-z0-9])APS\s*(\d+)", re.I)


@dataclass
class AuthItem:
    position: int
    kind: str
    label: str
    quantity: float | None
    source_row: str
    reason: str


@dataclass
class RequestCopy:
    """One stored line, used to decide which workbook copy is canonical."""

    line_id: str
    person_id: str | None
    source_file: str
    source_row: str
    source_hash: str
    service_date: Any
    amount_bs: Any
    diagnosis: str | None
    labels: tuple[str, ...]
    invoice_id: str | None = None
    referenced: bool = False


def aps_code_from_path(path: str | None) -> str | None:
    """``APS`` plus digits from a filename. ``APS.xls`` has no number."""
    if not path:
        return None
    match = _APS_RE.search(str(path).replace("\\", "/"))
    if not match:
        return None
    return f"APS {int(match.group(1))}"


def item_kind(sheet: str, label: str, column: str) -> str:
    blob = fold_header(f"{sheet} {label}")
    if "CONSULTA" in blob:
        return "consulta"
    if column == "ESTUDIO ESPECIAL" or "ESTUDIO" in fold_header(sheet):
        return "estudio"
    return "servicio"


def _label_columns(headers: list[Any]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for index, header in enumerate(headers):
        folded = fold_header(header)
        if folded in ITEM_COLUMNS:
            found.append((index, folded))
    return found


def _cell(row: list[Any], index: int) -> Any:
    if index < 0 or index >= len(row):
        return None
    return row[index]


def _label_text(value: Any) -> str | None:
    text = clean_name(value)
    if not text:
        return None
    if fold_header(text) in _SKIP_LABELS:
        return None
    return text


def _quantity(value: Any) -> float | None:
    """A whole-number neighbor is a quantity. A money amount is not."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not re.fullmatch(r"\d+(?:[.,]\d+)?", text):
            return None
        number = float(text.replace(",", "."))
    if number <= 0 or number >= 10000:
        return None
    if abs(number - round(number)) > 0.001:
        return None
    return float(round(number))


def parse_request_items(
    headers: list[Any],
    rows: list[list[Any]],
    data_index: int,
    sheet: str,
) -> list[AuthItem]:
    """Items on the person row and on the following rows that have no cédula."""
    if data_index < 0 or data_index >= len(rows):
        return []
    columns = _label_columns(headers)
    if not columns:
        return []
    items: list[AuthItem] = []

    def push(excel_row: int, label: str, quantity: float | None, column: str, reason: str) -> None:
        source_row = str(excel_row)
        if any(item.source_row == source_row for item in items):
            source_row = f"{excel_row}:{column}"
        items.append(
            AuthItem(
                position=len(items) + 1,
                kind=item_kind(sheet, label, column),
                label=label,
                quantity=quantity,
                source_row=source_row,
                reason=reason,
            )
        )

    person = rows[data_index]
    for col, column in columns:
        label = _label_text(_cell(person, col))
        if label:
            push(data_index + 1, label, None, column, "same_row")

    for index in range(data_index + 1, len(rows)):
        raw = list(rows[index])
        if row_has_person_signal(row_dict(headers, raw)):
            break
        excel_row = index + 1
        for col, column in columns:
            label = _label_text(_cell(raw, col))
            if not label:
                continue
            push(excel_row, label, _quantity(_cell(raw, col + 1)), column, "continuation")
    return items


def servicio_item(label: str, source_row: str) -> AuthItem:
    return AuthItem(
        position=1,
        kind="servicio",
        label=label,
        quantity=None,
        source_row=source_row,
        reason="service_label",
    )


def items_or_service(
    parsed: list[AuthItem],
    service_description: str | None,
    source_row: str,
) -> list[AuthItem]:
    """A sheet that already names the service, and has no study rows, gets one item."""
    if parsed:
        return parsed
    label = clean_name(service_description)
    if not label:
        return []
    return [servicio_item(label, source_row)]


def _date_key(value: Any) -> str:
    if value is None or value == "":
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def _amount_key(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return round(float(value), 2)


def request_key(line: RequestCopy) -> tuple:
    return (
        str(line.person_id or ""),
        _date_key(line.service_date),
        _amount_key(line.amount_bs),
        fold_header(line.diagnosis or ""),
        tuple(fold_header(label) for label in line.labels),
    )


def partition_copies(lines: list[RequestCopy]) -> list[tuple[RequestCopy, list[RequestCopy]]]:
    """Group identical requests. The single APS-numbered file is canonical.

    A copy that a factura or a review already points at stays visible.
    A different amount, diagnosis, or item list stays a separate request.
    """
    groups: dict[tuple, list[RequestCopy]] = {}
    for line in lines:
        groups.setdefault(request_key(line), []).append(line)

    partitioned: list[tuple[RequestCopy, list[RequestCopy]]] = []
    for group in groups.values():
        numbered = [line for line in group if aps_code_from_path(line.source_file)]
        if len(group) < 2 or len(numbered) != 1 or not group[0].labels:
            for line in group:
                partitioned.append((line, []))
            continue
        canonical = numbered[0]
        extras: list[RequestCopy] = []
        for line in group:
            if line.line_id == canonical.line_id:
                continue
            if line.invoice_id or line.referenced:
                partitioned.append((line, []))
                continue
            extras.append(line)
        partitioned.append((canonical, extras))
    return partitioned


def excel_row(source_row: str) -> str:
    """The row number inside ``SHEET:11``. The item key is that row, not the sheet."""
    if ":" not in source_row:
        return source_row
    return source_row.rsplit(":", 1)[1]


def source_ref(source_file: str, source_row: str) -> str:
    if ":" in source_row:
        sheet, row = source_row.rsplit(":", 1)
        return f"{source_file}#{sheet}:{row}"
    return f"{source_file}#{source_row}"
