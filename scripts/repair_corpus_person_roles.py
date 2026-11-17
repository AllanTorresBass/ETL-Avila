"""Corpus-wide titular/beneficiario repair from identity pages + FACT path.

For each invoice that has cedula/carnet/collage/pasaporte pages with exactly one
personal CI, promote that CI person as titular and link a different path patient
name as beneficiario. Uses the loader's shared guard (try_promote_ci_titular):
workbook titulars with CI/phone/DOB and existing plastic-ID titulars with another
CI are never swapped — those invoices, and packets with several CIs, are listed
for human review instead.

Dry-run by default; pass --apply to commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    extract_all_cedulas,
    extract_name_from_cedula_ocr,
    extract_titular_from_path,
)
from env_load import load_env
from ocr_invoice_pages import _read_cache
from person_upsert import upsert_by_ci
from upload_documents_to_blob import (
    _titular_ci_for_invoice,
    titular_promotion_blocker,
    try_promote_ci_titular,
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
        "skipped_no_ci": 0,
        "review_workbook_titular": 0,
        "review_ci_conflict": 0,
        "review_multiple_ci": 0,
    }
    review: list[tuple[str, str]] = []

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
                           d.person_id, sf.backup_path,
                           CASE WHEN p.identity_type = 'cedula'
                                THEN p.identity_number END AS linked_ci
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

                cis: list[str] = []
                ci_name = None
                backup_path = docs[0]["backup_path"]
                for doc in docs:
                    backup_path = doc["backup_path"] or backup_path
                    if doc.get("linked_ci") and doc["linked_ci"] not in cis:
                        cis.append(doc["linked_ci"])
                    cache = _read_cache(doc["backup_path"])
                    if not cache:
                        continue
                    text = _page_text(cache, int(doc["page_index"]))
                    for ci in extract_all_cedulas(text):
                        if ci not in cis:
                            cis.append(ci)
                    ci_name = ci_name or extract_name_from_cedula_ocr(text)

                if not cis:
                    stats["skipped_no_ci"] += 1
                    continue
                ci_digits = cis[0]
                if len(cis) > 1:
                    # Collages often mount titular + patient cards together. The
                    # current titular's CI among them is the clear insured; any
                    # other mix has no clear insured → escalate (skill rule).
                    current = _titular_ci_for_invoice(cur, str(inv["invoice_id"]))
                    if current not in cis:
                        stats["review_multiple_ci"] += 1
                        review.append((inv["invoice_number"], "multiple_ci"))
                        continue
                    ci_digits = current
                    ci_name = None  # OCR name may belong to the other card
                path_name, path_ci = extract_titular_from_path(backup_path or "")

                person_id, action = upsert_by_ci(
                    cur,
                    identity_number=ci_digits,
                    full_name=ci_name,
                    identity_type="cedula",
                    dry_run=not args.apply,
                )
                if person_id is None:
                    # Dry-run and the CI person does not exist yet.
                    stats["promoted"] += 1
                    if not args.quiet:
                        print(f"{inv['invoice_number']}: would create CI person + promote")
                    continue

                if not args.apply:
                    reason = titular_promotion_blocker(
                        cur, str(inv["invoice_id"]), str(person_id)
                    )
                    if reason:
                        stats[f"review_{reason}"] += 1
                        review.append((inv["invoice_number"], reason))
                    else:
                        stats["promoted"] += 1
                        if not args.quiet:
                            print(f"{inv['invoice_number']}: would promote ({action})")
                    continue

                outcome = try_promote_ci_titular(
                    cur,
                    str(inv["invoice_id"]),
                    str(person_id),
                    path_name=path_name,
                    path_ci=path_ci,
                )
                if outcome != "promoted":
                    stats[f"review_{outcome}"] += 1
                    review.append((inv["invoice_number"], outcome))
                    continue
                stats["promoted"] += 1

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
    if review:
        print(f"needs titular review ({len(review)}):")
        for number, reason in review:
            print(f"  FACT {number}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
