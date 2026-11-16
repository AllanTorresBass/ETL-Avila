"""Discover register workbooks under Avila-backup and read sheet headers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from openpyxl import load_workbook

from .canonical import SKIP_PATH_RE, fold_header, guess_family
from .normalize import map_headers, row_dict, row_has_person_signal

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "Avila-backup"


@dataclass
class SheetSpec:
    path: str
    sheet: str
    family: str
    headers: list[str]
    header_row: int
    mapped_fields: list[str]
    data_rows: int = 0


@dataclass
class WorkbookHit:
    path: str
    extension: str
    family: str
    sheets: list[SheetSpec] = field(default_factory=list)


def iter_workbook_paths(backup: Path = BACKUP) -> Iterator[Path]:
    if not backup.is_dir():
        return
    for path in sorted(backup.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".xlsx", ".xls"}:
            continue
        rel = str(path.relative_to(backup))
        if SKIP_PATH_RE.search(rel):
            continue
        if path.name.startswith("~$"):
            continue
        yield path


def _score_header_row(values: list[Any]) -> int:
    folded = [fold_header(v) for v in values if v not in (None, "")]
    if len(folded) < 3:
        return 0
    from .canonical import HEADER_ALIASES

    hits = sum(1 for h in folded if h in HEADER_ALIASES or h == "CEDULA DE IDENTIDAD")
    return hits


def find_header_row(rows: list[list[Any]], max_scan: int = 15) -> tuple[int, list[Any]]:
    best_i, best_score, best_row = 0, -1, rows[0] if rows else []
    for i, row in enumerate(rows[:max_scan]):
        score = _score_header_row(row)
        if score > best_score:
            best_i, best_score, best_row = i, score, row
    if best_score < 2:
        return -1, []
    return best_i, best_row


def read_xlsx_sheets(path: Path, relative: str) -> list[SheetSpec]:
    specs: list[SheetSpec] = []
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return specs
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            preview: list[list[Any]] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                preview.append(list(row))
                if i >= 40:
                    break
            header_idx, headers = find_header_row(preview)
            if header_idx < 0:
                continue
            header_labels = [("" if h is None else str(h).strip()) for h in headers]
            mapping = map_headers(headers)
            if len(mapping) < 2:
                continue
            family = guess_family(relative, header_labels)
            if family == "unknown" and len(mapping) < 3:
                continue
            # count data rows with person signal (bounded)
            data_rows = 0
            for row in preview[header_idx + 1 :]:
                normalized = row_dict(headers, list(row))
                if row_has_person_signal(normalized):
                    data_rows += 1
            # estimate remaining without full scan in discover
            specs.append(
                SheetSpec(
                    path=relative,
                    sheet=sheet_name,
                    family=family,
                    headers=header_labels,
                    header_row=header_idx + 1,
                    mapped_fields=sorted(set(mapping.values())),
                    data_rows=data_rows,
                )
            )
    finally:
        wb.close()
    return specs


def discover(backup: Path = BACKUP, *, limit: int = 0) -> list[WorkbookHit]:
    hits: list[WorkbookHit] = []
    for i, path in enumerate(iter_workbook_paths(backup)):
        if limit and i >= limit:
            break
        relative = str(path.relative_to(backup))
        if path.suffix.lower() == ".xls":
            # xlrd path — light support via optional reader in load
            hits.append(
                WorkbookHit(
                    path=relative,
                    extension=".xls",
                    family=guess_family(relative, []),
                    sheets=[],
                )
            )
            continue
        sheets = read_xlsx_sheets(path, relative)
        family = sheets[0].family if sheets else guess_family(relative, [])
        hits.append(
            WorkbookHit(path=relative, extension=path.suffix.lower(), family=family, sheets=sheets)
        )
    return hits


def write_inventory_csv(hits: list[WorkbookHit], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path",
                "extension",
                "family",
                "sheet",
                "header_row",
                "mapped_fields",
                "header_fingerprint",
                "preview_data_rows",
            ],
        )
        writer.writeheader()
        for hit in hits:
            if not hit.sheets:
                writer.writerow(
                    {
                        "path": hit.path,
                        "extension": hit.extension,
                        "family": hit.family,
                        "sheet": "",
                        "header_row": "",
                        "mapped_fields": "",
                        "header_fingerprint": "",
                        "preview_data_rows": 0,
                    }
                )
                continue
            for sheet in hit.sheets:
                writer.writerow(
                    {
                        "path": hit.path,
                        "extension": hit.extension,
                        "family": sheet.family,
                        "sheet": sheet.sheet,
                        "header_row": sheet.header_row,
                        "mapped_fields": "|".join(sheet.mapped_fields),
                        "header_fingerprint": "|".join(
                            fold_header(h) for h in sheet.headers if h
                        )[:500],
                        "preview_data_rows": sheet.data_rows,
                    }
                )


def iter_normalized_rows(
    path: Path,
    relative: str,
) -> Iterator[tuple[str, int, dict]]:
    """Yield (sheet_name, excel_row_number, canonical_row)."""
    if path.suffix.lower() == ".xls":
        yield from _iter_xls_rows(path, relative)
        return
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            preview: list[list[Any]] = []
            stream = ws.iter_rows(values_only=True)
            for i, row in enumerate(stream):
                preview.append(list(row))
                if i >= 40:
                    break
            header_idx, headers = find_header_row(preview)
            if header_idx < 0:
                continue
            mapping = map_headers(headers)
            if len(mapping) < 2:
                continue
            # Emit person rows already in the header preview window.
            for offset, row in enumerate(preview[header_idx + 1 :], start=header_idx + 2):
                normalized = row_dict(headers, list(row))
                if row_has_person_signal(normalized):
                    yield sheet_name, offset, normalized
            # Continue streaming the rest of the sheet (do not materialize all rows).
            next_row_number = len(preview) + 1
            for row in stream:
                normalized = row_dict(headers, list(row))
                if row_has_person_signal(normalized):
                    yield sheet_name, next_row_number, normalized
                next_row_number += 1
                if next_row_number > 5000:
                    break
    finally:
        wb.close()


def _iter_xls_rows(path: Path, relative: str) -> Iterator[tuple[str, int, dict]]:
    try:
        import xlrd
    except ImportError:
        return
    try:
        book = xlrd.open_workbook(path)
    except Exception:  # noqa: BLE001
        return
    for sheet in book.sheets():
        preview = [sheet.row_values(i) for i in range(min(sheet.nrows, 40))]
        header_idx, headers = find_header_row(preview)
        if header_idx < 0:
            continue
        mapping = map_headers(headers)
        if len(mapping) < 2:
            continue
        for r in range(header_idx + 1, sheet.nrows):
            values = sheet.row_values(r)
            # convert xlrd dates
            converted = []
            for c, val in enumerate(values):
                if sheet.cell_type(r, c) == xlrd.XL_CELL_DATE:
                    try:
                        converted.append(xlrd.xldate_as_datetime(val, book.datemode).date())
                    except Exception:  # noqa: BLE001
                        converted.append(val)
                else:
                    converted.append(val)
            normalized = row_dict(headers, converted)
            if not row_has_person_signal(normalized):
                continue
            yield sheet.name, r + 1, normalized
