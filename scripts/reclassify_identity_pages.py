"""Reclassify document pages from OCR cache with the current classifier.

Fixes mislabeled ID collage sheets and birth certificates that were stored as
cedula_identidad / otro_anexo. Scope: --invoices list, or --all loaded invoices.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    classify_document,
    extract_identity_number,
    extract_titular_from_path,
)
from env_load import load_env
from ocr_invoice_pages import _read_cache
from person_upsert import upsert_by_ci, upsert_by_name
from upload_documents_to_blob import (
    _link_path_name_as_beneficiario,
    link_invoice_person,
    promote_ci_person_as_titular,
)

AARON_FACTS = ("7316", "7394", "7759", "7798", "7799", "8322")
IDENTITY_TYPES = {
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
}


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
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reclassify every document page with invoice + OCR (corpus-wide)",
    )
    parser.add_argument(
        "--invoices",
        default="",
        help="Comma-separated invoice numbers (default: Aaron packets if not --all)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print transition summary (recommended for --all)",
    )
    parser.add_argument(
        "--suspect-only",
        action="store_true",
        help="Only pages currently typed as identity-related / otro_anexo / comprobante",
    )
    args = parser.parse_args()

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    stats = {"scanned": 0, "changed": 0, "skipped_no_ocr": 0, "person_linked": 0}
    transitions: Counter[str] = Counter()

    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if args.all:
                where = "d.page_index < 900"
                params: tuple = ()
            else:
                numbers = [
                    n.strip()
                    for n in (args.invoices or ",".join(AARON_FACTS)).split(",")
                    if n.strip()
                ]
                where = "i.invoice_number = ANY(%s) AND d.page_index < 900"
                params = (numbers,)

            if args.suspect_only:
                where += """
                  AND d.document_type::text = ANY(%s)
                """
                suspect = [
                    "cedula_identidad",
                    "otro_anexo",
                    "pasaporte",
                    "carnet",
                    "documentos_identificacion",
                    "acta_nacimiento",
                    "comprobante",
                ]
                params = params + (suspect,) if params else (suspect,)

            cur.execute(
                f"""
                SELECT d.id, d.page_index, d.document_type::text AS document_type,
                       d.evidence, d.person_id, d.invoice_id,
                       i.invoice_number, sf.backup_path
                FROM avila.document d
                JOIN avila.invoice i ON i.id = d.invoice_id
                JOIN avila.source_file sf ON sf.id = d.source_file_id
                WHERE {where}
                ORDER BY i.invoice_number, d.page_index
                """,
                params,
            )
            rows = cur.fetchall()

            for row in rows:
                stats["scanned"] += 1
                cache = _read_cache(row["backup_path"])
                if not cache:
                    stats["skipped_no_ocr"] += 1
                    continue
                text = _page_text(cache, int(row["page_index"]))
                new_type, new_evidence = classify_document(
                    text, backup_path=row["backup_path"]
                )
                if (
                    new_type == row["document_type"]
                    and new_evidence == (row["evidence"] or "")
                ):
                    continue

                key = f"{row['document_type']}→{new_type}"
                transitions[key] += 1
                stats["changed"] += 1
                if not args.quiet:
                    print(
                        f"{row['invoice_number']} p{row['page_index']}: "
                        f"{row['document_type']} → {new_type} ({new_evidence})"
                    )
                if not args.apply:
                    continue

                person_id = None
                if new_type in IDENTITY_TYPES:
                    identity = extract_identity_number(text)
                    if identity and identity[0] == "cedula":
                        person_id, _ = upsert_by_ci(
                            cur,
                            identity_number=identity[1],
                            identity_type="cedula",
                        )
                    if not person_id:
                        cur.execute(
                            """
                            SELECT p.id
                            FROM avila.invoice_person ip
                            JOIN avila.person p ON p.id = ip.person_id
                            WHERE ip.invoice_id = %s
                              AND ip.role = 'titular'
                              AND p.identity_number IS NOT NULL
                              AND p.identity_number <> ''
                            LIMIT 1
                            """,
                            (row["invoice_id"],),
                        )
                        titular = cur.fetchone()
                        if titular:
                            person_id = str(titular["id"])
                    if person_id:
                        promote_ci_person_as_titular(
                            cur, str(row["invoice_id"]), str(person_id)
                        )
                        path_name, _ = extract_titular_from_path(row["backup_path"])
                        if path_name:
                            _link_path_name_as_beneficiario(
                                cur,
                                str(row["invoice_id"]),
                                path_name,
                                str(person_id),
                            )
                        stats["person_linked"] += 1
                elif new_type == "acta_nacimiento":
                    path_name, _ = extract_titular_from_path(row["backup_path"])
                    if path_name:
                        person_id, _ = upsert_by_name(cur, full_name=path_name)
                        if person_id:
                            link_invoice_person(
                                cur,
                                str(row["invoice_id"]),
                                str(person_id),
                                "beneficiario",
                            )
                            stats["person_linked"] += 1

                if person_id is None and row["document_type"] == "cedula_identidad":
                    clear_person = True
                    person_id_sql = None
                elif person_id is not None:
                    clear_person = False
                    person_id_sql = person_id
                else:
                    clear_person = False
                    person_id_sql = row["person_id"]

                if clear_person:
                    cur.execute(
                        """
                        UPDATE avila.document
                        SET document_type = %s::avila.document_type,
                            evidence = %s,
                            person_id = NULL,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (new_type, new_evidence, row["id"]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE avila.document
                        SET document_type = %s::avila.document_type,
                            evidence = %s,
                            person_id = %s::uuid,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (new_type, new_evidence, person_id_sql, row["id"]),
                    )

        if args.apply:
            conn.commit()
            print("committed", stats)
        else:
            conn.rollback()
            print("dry-run", stats)

    print("transitions (top 30):")
    for key, n in transitions.most_common(30):
        print(f"  {n:5d}  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
