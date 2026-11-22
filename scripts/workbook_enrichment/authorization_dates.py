"""Dates for authorization lines: workbook columns, sentinels, and the sheet period.

A small number in a date column reads back as 1899/1900; those are not dates.
When a row has no date, the sheet or file name often names the month
(``ENERO 2025``); that month is a period, not a day.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .canonical import HEADER_ALIASES, fold_header
from .normalize import parse_date

MIN_YEAR = 2000

MONTHS = {
    "ENERO": 1, "ENE": 1,
    "FEBRERO": 2, "FEB": 2,
    "MARZO": 3, "MAR": 3,
    "ABRIL": 4, "ABR": 4,
    "MAYO": 5, "MAY": 5,
    "JUNIO": 6, "JUN": 6,
    "JULIO": 7, "JUL": 7,
    "AGOSTO": 8, "AGO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "SEPT": 9, "SEP": 9, "SET": 9,
    "OCTUBRE": 10, "OCT": 10,
    "NOVIEMBRE": 11, "NOV": 11,
    "DICIEMBRE": 12, "DIC": 12,
}
FULL_MONTHS = {name: number for name, number in MONTHS.items() if len(name) >= 5 or name == "MAYO"}
_MONTH_WORD = "|".join(sorted(MONTHS, key=len, reverse=True))
_FULL_MONTH_WORD = "|".join(sorted(FULL_MONTHS, key=len, reverse=True))
# Month, then up to 25 characters without a path separator, then a four-digit year.
_PERIOD = re.compile(rf"\b({_MONTH_WORD})\b[^/\d]{{0,25}}?(?:\d{{1,2}}[^/\d]{{1,10}})?\b(20\d{{2}})\b")
_MONTH_ONLY = re.compile(rf"\b({_FULL_MONTH_WORD})\b")
MAX_LAG_MONTHS = 6

# Date-like headers that are not about the request or the visit.
_NOT_SERVICE = ("NACIMIENTO", "FACTURA", "EMISION", "PAGO", "VENCIMIENTO", "ENTREGA", "INGRESO AL")

# Extra headers seen in the register workbooks, beyond canonical.HEADER_ALIASES.
EXTRA_DATE_HEADERS: dict[str, str] = {
    "FECHA": "request_date",
    "FECHA DE AUTORIZACION": "request_date",
    "FECHA AUTORIZACION": "request_date",
    "FECHA DE LA SOLICITUD": "request_date",
    "FECHA SOLICITUD": "request_date",
    "FECHA DE RECEPCION": "request_date",
    "FECHA RECEPCION": "request_date",
    "FECHA DE REGISTRO": "request_date",
    "FECHA DE CARGA": "request_date",
    "FECHA DE ENVIO": "request_date",
    "FECHA DE CONSULTA": "service_date",
    "FECHA CONSULTA": "service_date",
    "FECHA DE ESTUDIO": "service_date",
    "FECHA DEL SERVICIO": "service_date",
    "FECHA SERVICIO": "service_date",
    "FECHA DE ATENCION MEDICA": "service_date",
    "FECHA ATENCION": "service_date",
}


def real_date(value: Any) -> dt.date | None:
    """A parsed date, or None for blanks and Excel's 1899/1900 placeholders."""
    parsed = parse_date(value)
    if parsed is None or parsed.year < MIN_YEAR or parsed.year > dt.date.today().year + 1:
        return None
    return parsed


def is_sentinel(value: dt.date | None) -> bool:
    return value is not None and value.year < MIN_YEAR


def date_field(header: Any) -> str | None:
    folded = fold_header(header).rstrip(":").strip()
    if not folded:
        return None
    mapped = HEADER_ALIASES.get(folded) or EXTRA_DATE_HEADERS.get(folded)
    if mapped in ("request_date", "service_date"):
        return mapped
    return None


def is_date_header(header: Any) -> bool:
    folded = fold_header(header)
    return "FECHA" in folded and not any(word in folded for word in _NOT_SERVICE)


def date_columns(headers: list[Any]) -> dict[str, int]:
    """First column for request_date and service_date in this header row."""
    found: dict[str, int] = {}
    for index, header in enumerate(headers):
        field = date_field(header)
        if field and field not in found:
            found[field] = index
    return found


def row_dates(headers: list[Any], values: list[Any]) -> dict[str, dt.date]:
    dates: dict[str, dt.date] = {}
    for field, index in date_columns(headers).items():
        if index < len(values):
            parsed = real_date(values[index])
            if parsed:
                dates[field] = parsed
    return dates


def period_from_text(*texts: str | None) -> dt.date | None:
    """First month-and-year named in the texts (sheet name first, then file path)."""
    for text in texts:
        folded = fold_header(text or "")
        if not folded:
            continue
        for match in _PERIOD.finditer(folded):
            month = MONTHS[match.group(1)]
            year = int(match.group(2))
            if MIN_YEAR <= year <= dt.date.today().year + 1:
                return dt.date(year, month, 1)
    return None


def month_from_text(*texts: str | None) -> int | None:
    """A full Spanish month name with no year (``RELACION OCTUBRE LOTE I``)."""
    for text in texts:
        match = _MONTH_ONLY.search(fold_header(text or ""))
        if match:
            return FULL_MONTHS[match.group(1)]
    return None


def period_from_saved(month: int, saved: dt.date | None) -> dt.date | None:
    """The named month in the year that puts it at most MAX_LAG_MONTHS before the save date.

    Monthly relaciones are saved after the month they list, so a DICIEMBRE file
    saved in March 2024 lists December 2023.
    """
    if saved is None or saved.year < MIN_YEAR:
        return None
    year = saved.year if month <= saved.month else saved.year - 1
    lag = (saved.year - year) * 12 + saved.month - month
    if lag > MAX_LAG_MONTHS:
        return None
    return dt.date(year, month, 1)
