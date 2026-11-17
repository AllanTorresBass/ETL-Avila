"""Reclassify document pages from OCR cache with the current classifier.

Fixes mislabeled ID collage sheets and birth certificates that were stored as
cedula_identidad / otro_anexo. Scope: --invoices list, or --all loaded invoices.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    classify_document,
    extract_name_from_cedula_ocr,
    extract_titular_from_path,
)
from env_load import load_env
import provenance
from ocr_invoice_pages import _read_cache
from person_upsert import upsert_by_ci, upsert_by_name
from upload_documents_to_blob import (
    _titular_ci_for_invoice,
    identity_page_ci,
    link_invoice_person,
    try_promote_ci_titular,
)

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


def _demote_false_titular(cur, row: dict) -> bool:
    """A page that was typed as an ID card is really an acta.

    If its person is titular on this invoice only through ``ocr_cedula`` and no
    other identity page of the invoice points at them, the titular came from a
    parent/registrar CI quoted in the acta — set that link to ``unknown`` so a
    human (or a real ID page) decides. Returns True when a row was changed.
    """
    cur.execute(
        """
        UPDATE avila.invoice_person ip
        SET role = 'unknown'
        WHERE ip.invoice_id = %s
          AND ip.person_id = %s
          AND ip.role = 'titular'
          AND ip.source = 'ocr_cedula'
          AND NOT EXISTS (
            SELECT 1 FROM avila.document d
            WHERE d.invoice_id = ip.invoice_id
              AND d.person_id = ip.person_id
              AND d.id <> %s
              AND d.document_type::text = ANY(%s)
          )
        RETURNING 1
        """,
        (row["invoice_id"], row["person_id"], row["id"], sorted(IDENTITY_TYPES)),
    )
    return cur.fetchone() is not None


def _reclassify_rows(cur, rows, args, stats: dict, transitions: Counter, review: list[str]) -> None:
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

        provenance.record(
            cur,
            entity="document",
            entity_id=row["id"],
            field="document_type",
            old=row["document_type"],
            new=new_type,
            rule_id=f"classify:{new_evidence}"[:80],
            source_kind="ocr",
            source_ref=f"{row['backup_path']}#{row['page_index']}",
            reason="reclassify",
        )
        person_id = None
        if new_type in IDENTITY_TYPES:
            ci, ci_status = identity_page_ci(
                text, _titular_ci_for_invoice(cur, str(row["invoice_id"]))
            )
            if ci_status == "multiple":
                stats["titular_review"] += 1
                review.append(f"FACT {row['invoice_number']} p{row['page_index']}: multiple_ci")
                provenance.open_review(
                    cur,
                    kind="multiple_ci",
                    dedupe_key=f"multiple_ci:{row['invoice_id']}:{row['page_index']}",
                    invoice_id=row["invoice_id"],
                    document_id=row["id"],
                )
            elif ci:
                person_id, _ = upsert_by_ci(
                    cur,
                    identity_number=ci,
                    full_name=extract_name_from_cedula_ocr(text),
                    identity_type="cedula",
                )
            if person_id:
                path_name, path_ci = extract_titular_from_path(row["backup_path"])
                outcome = try_promote_ci_titular(
                    cur,
                    str(row["invoice_id"]),
                    str(person_id),
                    path_name=path_name,
                    path_ci=path_ci,
                )
                if outcome == "promoted":
                    stats["person_linked"] += 1
                else:
                    stats["titular_review"] += 1
                    review.append(
                        f"FACT {row['invoice_number']} p{row['page_index']}: {outcome}"
                    )
            elif ci_status == "none":
                # Weak OCR (e.g. collage with only a provider RIF): attach the
                # page to the existing CI titular without changing roles.
                cur.execute(
                    """
                    SELECT p.id
                    FROM avila.invoice_person ip
                    JOIN avila.person p ON p.id = ip.person_id
                    WHERE ip.invoice_id = %s
                      AND ip.role = 'titular'
                      AND p.identity_type = 'cedula'
                      AND p.identity_number IS NOT NULL
                    LIMIT 1
                    """,
                    (row["invoice_id"],),
                )
                titular = cur.fetchone()
                if titular:
                    person_id = str(titular["id"])
        elif new_type == "acta_nacimiento":
            if row["document_type"] in IDENTITY_TYPES and row["person_id"]:
                if _demote_false_titular(cur, row):
                    stats["false_titular_demoted"] += 1
                    review.append(
                        f"FACT {row['invoice_number']} p{row['page_index']}: "
                        "titular came from an acta page → set to unknown"
                    )
                    provenance.record(
                        cur,
                        entity="invoice_person",
                        entity_id=f"{row['invoice_id']}:{row['person_id']}",
                        field="role",
                        old="titular",
                        new="unknown",
                        rule_id="acta_demotes_false_titular",
                    )
                    provenance.open_review(
                        cur,
                        kind="acta_titular",
                        dedupe_key=f"acta_titular:{row['invoice_id']}:{row['person_id']}",
                        person_id=row["person_id"],
                        invoice_id=row["invoice_id"],
                        document_id=row["id"],
                    )
            path_name, _ = extract_titular_from_path(row["backup_path"])
            if path_name:
                person_id, _ = upsert_by_name(cur, full_name=path_name)
                if person_id:
                    link_invoice_person(
                        cur,
                        str(row["invoice_id"]),
                        str(person_id),
                        "beneficiario",
                        source="path",
                        rule_id="acta_path_beneficiario",
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
        help="Comma-separated invoice numbers (required unless --all)",
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
    if not args.all and not args.invoices.strip():
        parser.error("pass --invoices a,b,c or --all")

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    stats = {
        "scanned": 0,
        "changed": 0,
        "skipped_no_ocr": 0,
        "person_linked": 0,
        "titular_review": 0,
        "false_titular_demoted": 0,
    }
    review: list[str] = []
    transitions: Counter[str] = Counter()
    provenance.start_run(url, "reclassify_identity_pages", vars(args), apply=args.apply)

    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if args.all:
                where = "d.page_index < 900"
                params: tuple = ()
            else:
                numbers = [
                    n.strip()
                    for n in args.invoices.split(",")
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

            # Neon round trips dominate; the pipeline sends writes without waiting
            # and only syncs when a helper fetches a row.
            batch = conn.pipeline() if args.apply else contextlib.nullcontext()
            with batch:
                _reclassify_rows(cur, rows, args, stats, transitions, review)

        if args.apply:
            conn.commit()
            print("committed", stats)
        else:
            conn.rollback()
            print("dry-run", stats)
    provenance.finish_run(url, {**stats, **{f"t:{k}": v for k, v in transitions.items()}})

    if review:
        print(f"needs review ({len(review)}):")
        for line in review:
            print(f"  {line}")
    print("transitions (top 30):")
    for key, n in transitions.most_common(30):
        print(f"  {n:5d}  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
