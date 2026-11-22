#!/usr/bin/env python3
"""Counts-only audit of authorization lines: links, dates, providers, and causes.

  PYTHONPATH=scripts .venv/bin/python scripts/authorization_audit.py
  PYTHONPATH=scripts .venv/bin/python scripts/authorization_audit.py --headers --label baseline

Writes output/runs/authorization-audit[-label].md. ``--headers`` also opens each
workbook that carries a line and lists date-like headers that are not mapped to
request_date or service_date. Read-only. Stdout is counts.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_load import load_env  # noqa: E402
from workbook_enrichment.authorization_dates import date_field, is_date_header  # noqa: E402
from workbook_enrichment.canonical import fold_header  # noqa: E402
from workbook_enrichment.discover import BACKUP, find_header_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "runs"

CAUSE_SQL = """
SELECT
  CASE
    WHEN al.duplicate_of IS NOT NULL THEN 'duplicate'
    WHEN al.invoice_id IS NOT NULL THEN 'linked'
    WHEN al.person_id IS NULL AND al.titular_person_id IS NULL THEN 'no_person'
    WHEN EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = al.person_id)
      THEN 'person_has_factura'
    WHEN EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = al.titular_person_id)
      THEN 'titular_has_factura'
    ELSE 'no_factura_for_person'
  END AS cause,
  count(*)::int AS n
FROM avila.authorization_line al
GROUP BY 1 ORDER BY 2 DESC
"""

FOLDER_SQL = """
SELECT split_part(source_file, '/', 1) AS folder,
       count(*)::int AS lines,
       count(invoice_id)::int AS linked,
       count(*) FILTER (WHERE coalesce(request_date, service_date) IS NULL
                          OR coalesce(request_date, service_date) < DATE '2000-01-01')::int AS no_date
FROM avila.authorization_line
GROUP BY 1 ORDER BY 2 DESC
"""

TOTALS_SQL = """
SELECT count(*)::int AS lines,
       count(invoice_id)::int AS linked,
       count(*) FILTER (WHERE coalesce(request_date, service_date) IS NULL)::int AS no_date,
       count(*) FILTER (WHERE coalesce(request_date, service_date) < DATE '2000-01-01')::int AS sentinel_date,
       count(*) FILTER (WHERE person_id IS NULL)::int AS no_person,
       count(*) FILTER (WHERE titular_person_id IS NOT NULL)::int AS with_titular,
       count(*) FILTER (WHERE nullif(btrim(clave_rms), '') IS NOT NULL)::int AS with_clave,
       count(*) FILTER (WHERE nullif(btrim(provider_name), '') IS NULL)::int AS no_provider,
       count(DISTINCT nullif(btrim(provider_name), ''))::int AS provider_spellings,
       count(*) FILTER (WHERE coalesce(amount_bs, 0) = 0 AND coalesce(amount_usd, 0) = 0)::int AS no_amount,
       count(*) FILTER (WHERE duplicate_of IS NOT NULL)::int AS duplicates
FROM avila.authorization_line
"""

OPTIONAL_SQL = {
    "match_status": "SELECT coalesce(match_status, '(none)') AS k, count(*)::int AS n FROM avila.authorization_line GROUP BY 1 ORDER BY 2 DESC",
    "date_source": "SELECT coalesce(date_source, '(none)') AS k, count(*)::int AS n FROM avila.authorization_line GROUP BY 1 ORDER BY 2 DESC",
    "provider_code": "SELECT coalesce(provider_code, '(none)') AS k, count(*)::int AS n FROM avila.authorization_line GROUP BY 1 ORDER BY 2 DESC LIMIT 12",
}


def _table(title: str, header: tuple[str, ...], rows: list[tuple]) -> list[str]:
    lines = [f"## {title}", "", "| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return lines + [""]


def header_audit(cur) -> tuple[Counter, Counter, Counter]:
    from repair_authorization_items import _load_sheets

    cur.execute("SELECT source_file, source_row FROM avila.authorization_line")
    by_file: dict[str, Counter] = {}
    for row in cur.fetchall():
        sheet = row["source_row"].rsplit(":", 1)[0]
        by_file.setdefault(row["source_file"], Counter())[sheet] += 1
    unmapped: Counter = Counter()
    mapped: Counter = Counter()
    status: Counter = Counter()
    for source_file, sheets_used in by_file.items():
        path = BACKUP / source_file
        if not path.is_file():
            status["files_missing"] += 1
            status["lines_file_missing"] += sum(sheets_used.values())
            continue
        try:
            sheets = _load_sheets(path)
        except Exception:  # noqa: BLE001
            status["file_errors"] += 1
            continue
        for sheet, lines in sheets_used.items():
            rows = sheets.get(sheet) or sheets.get(sheet.strip()) or []
            _, headers = find_header_row(rows) if rows else (-1, [])
            has_date = False
            for header in headers:
                if not is_date_header(header):
                    continue
                if date_field(header):
                    mapped[fold_header(header)] += lines
                    has_date = True
                else:
                    unmapped[fold_header(header)] += lines
            status["lines_with_date_column" if has_date else "lines_without_date_column"] += lines
    return mapped, unmapped, status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--headers", action="store_true", help="Also open workbooks and audit date headers")
    parser.add_argument("--label", default="", help="Suffix for the report file name")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    report: list[str] = ["# Authorization audit", ""]
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        conn.read_only = True
        cur.execute(TOTALS_SQL)
        totals = cur.fetchone()
        report += _table("Totals", ("Counter", "Value"), [(k, v) for k, v in totals.items()])
        cur.execute(CAUSE_SQL)
        causes = cur.fetchall()
        report += _table("Link status and cause", ("Cause", "Lines"), [(r["cause"], r["n"]) for r in causes])
        cur.execute(FOLDER_SQL)
        report += _table(
            "By insurer folder",
            ("Folder", "Lines", "Linked", "No date"),
            [(r["folder"], r["lines"], r["linked"], r["no_date"]) for r in cur.fetchall()],
        )
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'avila' AND table_name = 'authorization_line'"
        )
        columns = {r["column_name"] for r in cur.fetchall()}
        for column, sql in OPTIONAL_SQL.items():
            if column in columns:
                cur.execute(sql)
                report += _table(column, (column, "Lines"), [(r["k"], r["n"]) for r in cur.fetchall()])
        if args.headers:
            mapped, unmapped, status = header_audit(cur)
            report += _table("Workbook date columns", ("Counter", "Lines"), sorted(status.items()))
            report += _table("Mapped date headers", ("Header", "Lines"), mapped.most_common())
            report += _table("Unmapped date-like headers", ("Header", "Lines"), unmapped.most_common(40))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"authorization-audit-{args.label}.md" if args.label else "authorization-audit.md"
    (OUT_DIR / name).write_text("\n".join(report), encoding="utf-8")
    print(f"lines={totals['lines']} linked={totals['linked']} no_date={totals['no_date']} "
          f"sentinel_date={totals['sentinel_date']} report=output/runs/{name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
