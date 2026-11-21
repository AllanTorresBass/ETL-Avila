#!/usr/bin/env python3
"""Read each factura's pages into one local truth row. No Neon writes.

One JSON object per loaded invoice, from the fiscal sheet, the identity cards,
and any acta. Parent numbers that appear only on an acta are listed and not
treated as a card. The folder name is stored as a hint.

  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth.py
  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth.py --limit 20
  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth.py --invoices 12843,7394

Stdout and output/runs/invoice-truth.md are counts only.
PHI stays in output/runs/invoice-truth.jsonl (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (  # noqa: E402
    extract_all_cedulas,
    extract_name_from_cedula_ocr,
    extract_titular_from_path,
)
from env_load import load_env  # noqa: E402
from fiscal_extract import FiscalFields, extract  # noqa: E402
from ocr_invoice_pages import _read_cache  # noqa: E402
from person_name_gate import sanitize_person_name  # noqa: E402
from role_cohorts import IDENTITY_DOC_TYPES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_JSONL = ROOT / "output" / "runs" / "invoice-truth.jsonl"
OUT_MD = ROOT / "output" / "runs" / "invoice-truth.md"

CARD_TYPES = frozenset(IDENTITY_DOC_TYPES)
READ_TYPES = CARD_TYPES | {"factura_fiscal", "acta_nacimiento"}


def page_text(backup_path: str | None, page_index: int | None, cache: dict[str, dict | None]) -> str:
    """OCR text for one 1-based page. Missing cache or a short page is empty."""
    if not backup_path or page_index is None:
        return ""
    if backup_path not in cache:
        cache[backup_path] = _read_cache(backup_path)
    record = cache[backup_path]
    if not record:
        return ""
    pages = record.get("pages") or []
    idx = int(page_index) - 1
    if 0 <= idx < len(pages):
        return pages[idx].get("text") or ""
    return ""


def _dedupe(numbers: list[str]) -> list[str]:
    seen: list[str] = []
    for number in numbers:
        if number and number not in seen:
            seen.append(number)
    return seen


def build_record(invoice_id: str, invoice_number: str, pages: list[dict], text_for) -> dict:
    """Assemble one truth row from already-loaded document rows and a text reader."""
    fields = FiscalFields()
    fiscal_backup = None
    fiscal_page = None
    cards: list[dict] = []
    acta_found: list[str] = []
    paths: list[str] = []

    for page in pages:
        backup = page.get("backup_path") or ""
        if backup and backup not in paths:
            paths.append(backup)
        doc_type = page.get("document_type") or ""
        if doc_type not in READ_TYPES:
            continue
        text = text_for(backup, page.get("page_index"))
        if doc_type == "factura_fiscal":
            found = extract(text)
            if fiscal_backup is None and (
                found.titular_ci or found.titular_name or found.patient_name or found.patient_ci
            ):
                fiscal_backup = backup or None
                fiscal_page = page.get("page_index")
            fields.merge(found)
            continue
        if doc_type == "acta_nacimiento":
            acta_found.extend(extract_all_cedulas(text))
            continue
        cards.append(
            {
                "document_id": page.get("document_id"),
                "page_index": page.get("page_index"),
                "document_type": doc_type,
                "backup_path": backup or None,
                "name": sanitize_person_name(extract_name_from_cedula_ocr(text)),
                "cedulas": extract_all_cedulas(text),
            }
        )

    card_cis = {ci for card in cards for ci in card["cedulas"]}
    path_name = None
    path_ci = None
    ordered = sorted(paths, key=lambda raw: (0 if "FACT" in raw.upper() else 1, raw))
    for raw in ordered:
        name, ci = extract_titular_from_path(raw)
        if name or ci:
            path_name = sanitize_person_name(name)
            path_ci = ci
            break

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "fiscal_titular_name": sanitize_person_name(fields.titular_name),
        "fiscal_titular_ci": fields.titular_ci,
        "fiscal_patient_name": sanitize_person_name(fields.patient_name),
        "fiscal_patient_ci": fields.patient_ci,
        "fiscal_backup_path": fiscal_backup,
        "fiscal_page_index": fiscal_page,
        "cards": cards,
        "acta_parent_cis": [ci for ci in _dedupe(acta_found) if ci not in card_cis],
        "path_name": path_name,
        "path_ci": path_ci,
    }


def count_record(row: dict, stats: Counter) -> None:
    stats["invoices"] += 1
    if row.get("fiscal_titular_name") or row.get("fiscal_titular_ci"):
        stats["fiscal_titular"] += 1
    if row.get("fiscal_patient_name") or row.get("fiscal_patient_ci"):
        stats["fiscal_patient"] += 1
    cis = _dedupe([ci for card in row.get("cards") or [] for ci in card.get("cedulas") or []])
    if len(cis) == 1:
        stats["card_ci_one"] += 1
    elif len(cis) >= 2:
        stats["card_ci_many"] += 1
    else:
        stats["card_ci_none"] += 1


def render_md(stats: Counter) -> str:
    lines = [
        "# Invoice truth",
        "",
        "Counts only. Names and cédulas stay in `invoice-truth.jsonl`.",
        "",
        "| Counter | Value |",
        "| --- | ---: |",
        f"| Facturas read | {stats['invoices']} |",
        f"| Fiscal titular line | {stats['fiscal_titular']} |",
        f"| Fiscal patient line | {stats['fiscal_patient']} |",
        f"| One card cédula | {stats['card_ci_one']} |",
        f"| Two or more card cédulas | {stats['card_ci_many']} |",
        f"| No card cédula | {stats['card_ci_none']} |",
        "",
    ]
    return "\n".join(lines)


def _wanted(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def load_pages(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
          i.id::text AS invoice_id,
          i.invoice_number,
          d.id::text AS document_id,
          d.page_index,
          d.document_type::text AS document_type,
          sf.backup_path
        FROM avila.invoice i
        LEFT JOIN avila.document d ON d.invoice_id = i.id
        LEFT JOIN avila.source_file sf ON sf.id = d.source_file_id
        ORDER BY i.invoice_number, sf.backup_path NULLS LAST, d.page_index NULLS LAST
        """
    )
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in cur.fetchall():
        invoice_id = row["invoice_id"]
        if invoice_id not in grouped:
            grouped[invoice_id] = {
                "invoice_id": invoice_id,
                "invoice_number": row["invoice_number"],
                "pages": [],
            }
            order.append(invoice_id)
        if row["document_id"]:
            grouped[invoice_id]["pages"].append(row)
    return [grouped[key] for key in order]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many facturas")
    parser.add_argument("--invoices", help="Comma-separated factura numbers")
    args = parser.parse_args()
    wanted = _wanted(args.invoices)
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")

    stats: Counter = Counter()
    cache: dict[str, dict | None] = {}
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        invoices = load_pages(cur)
        conn.rollback()
    if wanted is not None:
        invoices = [row for row in invoices if row["invoice_number"] in wanted]
    if args.limit:
        invoices = invoices[: args.limit]

    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for row in invoices:
            record = build_record(
                row["invoice_id"],
                row["invoice_number"],
                row["pages"],
                lambda path, index: page_text(path, index, cache),
            )
            count_record(record, stats)
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            if stats["invoices"] % 500 == 0:
                print(f"read {stats['invoices']}", flush=True)

    OUT_MD.write_text(render_md(stats), encoding="utf-8")
    print(
        "invoices",
        stats["invoices"],
        "fiscal_titular",
        stats["fiscal_titular"],
        "fiscal_patient",
        stats["fiscal_patient"],
        "card_ci_one",
        stats["card_ci_one"],
        "card_ci_many",
        stats["card_ci_many"],
        "card_ci_none",
        stats["card_ci_none"],
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
