"""Corpus-wide titular/beneficiario repair from identity pages + FACT path.

For each invoice that has cedula/carnet/collage/pasaporte pages (or a CI on
those pages' OCR), promote the CI person as titular and demote a different
path patient name to beneficiario. Skips swapping when the current titular is
workbook-sourced with CI/phone/DOB and the page CI differs.

Dry-run by default; pass --apply to commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import extract_identity_number, extract_titular_from_path
from env_load import load_env
from ocr_invoice_pages import _read_cache
from person_upsert import upsert_by_ci
from upload_documents_to_blob import (
    _link_path_name_as_beneficiario,
    promote_ci_person_as_titular,
)

IDENTITY_TYPES = (
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
)


def _page_text(cache: dict, page_index: int) -> str:
    pages = cache.get("pages") or []
    if not isinstance(pages, list) or page_index < 1 or page_index > len(pages):
        return ""
    page = pages[page_index - 1]
    if isinstance(page, dict):
        return page.get("text") or ""
    return str(page or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    stats = {
        "invoices": 0,
        "promoted": 0,
        "beneficiario_linked": 0,
        "skipped_workbook_conflict": 0,
        "skipped_no_ci": 0,
    }

    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT i.id AS invoice_id, i.invoice_number
                FROM avila.invoice i
                JOIN avila.document d ON d.invoice_id = i.id
                WHERE d.document_type::text = ANY(%s)
                  AND d.page_index < 900
                ORDER BY i.invoice_number
                """,
                (list(IDENTITY_TYPES),),
            )
            invoices = cur.fetchall()

            for inv in invoices:
                stats["invoices"] += 1
                cur.execute(
                    """
                    SELECT d.page_index, d.document_type::text AS document_type,
                           d.person_id, sf.backup_path, p.identity_number AS linked_ci
                    FROM avila.document d
                    JOIN avila.source_file sf ON sf.id = d.source_file_id
                    LEFT JOIN avila.person p ON p.id = d.person_id
                    WHERE d.invoice_id = %s
                      AND d.document_type::text = ANY(%s)
                      AND d.page_index < 900
                    ORDER BY d.page_index
                    """,
                    (inv["invoice_id"], list(IDENTITY_TYPES)),
                )
                docs = cur.fetchall()
                if not docs:
                    continue

                ci_digits = None
                backup_path = docs[0]["backup_path"]
                for doc in docs:
                    backup_path = doc["backup_path"] or backup_path
                    if doc.get("linked_ci"):
                        ci_digits = doc["linked_ci"]
                        break
                    cache = _read_cache(doc["backup_path"])
                    if not cache:
                        continue
                    text = _page_text(cache, int(doc["page_index"]))
                    identity = extract_identity_number(text)
                    if identity and identity[0] == "cedula":
                        ci_digits = identity[1]
                        break

                if not ci_digits:
                    stats["skipped_no_ci"] += 1
                    continue

                # Workbook conflict guard
                cur.execute(
                    """
                    SELECT ip.source, p.id, p.identity_number, p.phone, p.birth_date
                    FROM avila.invoice_person ip
                    JOIN avila.person p ON p.id = ip.person_id
                    WHERE ip.invoice_id = %s AND ip.role = 'titular'
                    LIMIT 1
                    """,
                    (inv["invoice_id"],),
                )
                existing = cur.fetchone()
                if (
                    existing
                    and existing.get("source") == "workbook"
                    and existing.get("identity_number")
                    and existing["identity_number"] != ci_digits
                    and (existing.get("phone") or existing.get("birth_date"))
                ):
                    stats["skipped_workbook_conflict"] += 1
                    if not args.quiet:
                        print(
                            f"{inv['invoice_number']}: skip workbook conflict "
                            f"{existing['identity_number']} vs page CI {ci_digits}"
                        )
                    continue

                person_id, _ = upsert_by_ci(
                    cur, identity_number=ci_digits, identity_type="cedula"
                )
                if not person_id:
                    stats["skipped_no_ci"] += 1
                    continue

                if not args.apply:
                    path_name, _ = extract_titular_from_path(backup_path or "")
                    if not args.quiet:
                        print(
                            f"{inv['invoice_number']}: would promote CI {ci_digits}"
                            + (f" + beneficiario {path_name!r}" if path_name else "")
                        )
                    stats["promoted"] += 1
                    if path_name:
                        stats["beneficiario_linked"] += 1
                    continue

                promote_ci_person_as_titular(
                    cur, str(inv["invoice_id"]), str(person_id)
                )
                stats["promoted"] += 1
                path_name, _ = extract_titular_from_path(backup_path or "")
                if path_name:
                    linked = _link_path_name_as_beneficiario(
                        cur, str(inv["invoice_id"]), path_name, str(person_id)
                    )
                    if linked:
                        stats["beneficiario_linked"] += 1

                # Attach identity docs without person_id to the CI person
                cur.execute(
                    """
                    UPDATE avila.document
                    SET person_id = %s::uuid, updated_at = now()
                    WHERE invoice_id = %s
                      AND document_type::text = ANY(%s)
                      AND person_id IS NULL
                      AND page_index < 900
                    """,
                    (person_id, inv["invoice_id"], list(IDENTITY_TYPES)),
                )

        if args.apply:
            conn.commit()
            print("committed", stats)
        else:
            conn.rollback()
            print("dry-run", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
