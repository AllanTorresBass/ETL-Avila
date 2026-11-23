#!/usr/bin/env python3
"""Repair authorization line dates and record where each date came from.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_authorization_dates.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/repair_authorization_dates.py --apply

For each line, reread its own workbook row:

- A real date in a request or service column is kept (``date_source`` request or service).
- A stored 1899/1900 date is cleared. Those cells held small numbers (Seguros
  Venezuela's FECHA DE LA CITA is a 1-16 row counter), so no day is rebuilt from them.
- With no date at all, ``period_month`` is the month named in the sheet or file.
  A name with no year takes the year from the workbook save date, when the save
  is at most six months after that month.

A real stored date is never overwritten. Each change records field provenance.
Stdout is counts only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from repair_authorization_items import _load_sheets  # noqa: E402
from workbook_enrichment.authorization_dates import (  # noqa: E402
    date_columns,
    is_sentinel,
    month_from_text,
    period_from_saved,
    period_from_text,
    real_date,
)
from workbook_enrichment.discover import BACKUP, find_header_row  # noqa: E402

RULE = "authorization_date_repair"


class Workbook:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.sheets: dict[str, list[list]] = {}
        self.saved: dt.date | None = None
        self.headers: dict[str, tuple[int, list]] = {}
        if not path.is_file():
            return
        try:
            self.sheets = _load_sheets(path)
        except Exception:  # noqa: BLE001
            self.sheets = {}
        self.saved = saved_date(path)

    def row(self, sheet: str, excel_row: int) -> tuple[list, list]:
        rows = self.sheets.get(sheet) or self.sheets.get(sheet.strip()) or []
        if not rows:
            return [], []
        if sheet not in self.headers:
            self.headers[sheet] = find_header_row(rows)
        header_index, headers = self.headers[sheet]
        index = excel_row - 1
        if header_index < 0 or not header_index < index < len(rows):
            return list(headers), []
        return list(headers), list(rows[index])


def saved_date(path: Path) -> dt.date | None:
    if path.suffix.lower() == ".xlsx":
        try:
            from openpyxl import load_workbook

            book = load_workbook(path, read_only=True)
            try:
                modified = book.properties.modified
            finally:
                book.close()
            if modified:
                return modified.date()
        except Exception:  # noqa: BLE001
            pass
    try:
        return dt.date.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def plan_line(line: dict, book: Workbook) -> dict:
    """What this line's dates should be. Keys: request_date, service_date, date_source, period_month."""
    sheet, _, row_text = line["source_row"].rpartition(":")
    name = Path(line["source_file"]).name
    period = period_from_text(sheet, name, line["source_file"])
    period_origin = "named" if period else None
    if period is None:
        month = month_from_text(name, sheet)
        if month:
            period = period_from_saved(month, book.saved)
            period_origin = "saved" if period else None

    headers, values = book.row(sheet, int(row_text)) if row_text.isdigit() else ([], [])
    columns = date_columns(headers)
    plan = {
        "request_date": line["request_date"],
        "service_date": line["service_date"],
        "date_source": None,
        "period_month": None,
        "period_origin": period_origin,
        "rebuilt": [],
        "cleared": [],
    }
    for field in ("request_date", "service_date"):
        stored = line[field]
        if stored is not None and not is_sentinel(stored):
            continue
        index = columns.get(field)
        cell = values[index] if index is not None and index < len(values) else None
        exact = real_date(cell)
        if exact:
            plan[field] = exact
            plan["rebuilt"].append(field)
        elif stored is not None:
            plan[field] = None
            plan["cleared"].append(field)

    for field, source in (("request_date", "request"), ("service_date", "service")):
        if plan[field] is not None:
            plan["date_source"] = source
            break
    else:
        if period is not None:
            plan["date_source"] = "period"
            plan["period_month"] = period
    return plan


def run(cur, counts: Counter) -> None:
    cur.execute(
        """
        SELECT id::text AS id, source_file, source_row, request_date, service_date,
               date_source, period_month
        FROM avila.authorization_line
        """
    )
    lines = cur.fetchall()
    books: dict[str, Workbook] = {}
    counts["lines"] = len(lines)
    for line in lines:
        source = line["source_file"]
        if source not in books:
            path = Path(source) if Path(source).is_absolute() else BACKUP / source
            books[source] = Workbook(path)
            if not books[source].sheets:
                counts["files_unreadable"] += 1
        plan = plan_line(line, books[source])
        if plan["period_origin"]:
            counts[f"period_{plan['period_origin']}"] += 1
        for field in plan["rebuilt"]:
            counts[f"rebuilt_{field}"] += 1
        for field in plan["cleared"]:
            counts[f"cleared_{field}"] += 1
        counts[f"date_source_{plan['date_source'] or 'none'}"] += 1

        changes = {
            field: (line[field], plan[field])
            for field in ("request_date", "service_date", "date_source", "period_month")
            if line[field] != plan[field]
        }
        if not changes:
            continue
        counts["lines_changed"] += 1
        cur.execute(
            """
            UPDATE avila.authorization_line
            SET request_date = %s, service_date = %s, date_source = %s, period_month = %s, updated_at = now()
            WHERE id = %s::uuid
            """,
            (plan["request_date"], plan["service_date"], plan["date_source"], plan["period_month"], line["id"]),
        )
        reason = ",".join(
            part for part in (
                f"period:{plan['period_origin']}" if plan["period_origin"] else "",
                "rebuilt:" + "+".join(plan["rebuilt"]) if plan["rebuilt"] else "",
                "cleared:" + "+".join(plan["cleared"]) if plan["cleared"] else "",
            ) if part
        ) or None
        for field, (old, new) in changes.items():
            provenance.record(
                cur,
                entity="authorization_line",
                entity_id=line["id"],
                field=field,
                old=old,
                new=new,
                rule_id=RULE,
                source_kind="workbook",
                source_ref=f"{source}#{line['source_row']}",
                reason=reason,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "repair_authorization_dates", vars(args), apply=args.apply)
    counts: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.pipeline(), conn.cursor() as cur:
            run(cur, counts)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(counts))
    print("apply" if args.apply else "dry-run", dict(sorted(counts.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
