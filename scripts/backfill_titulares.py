"""Link each existing invoice to its titular person (from source paths / OCR).

Safe to run while the Blob loader is uploading: only writes person + invoice_person.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import extract_titular_from_ocr, extract_titular_from_path
from env_load import load_env
from ocr_invoice_pages import _read_cache
from upload_documents_to_blob import ensure_invoice_titular


def main() -> None:
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL missing")
    linked = skipped = 0
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id AS invoice_id, i.invoice_number,
                       sf.backup_path, sf.file_label
                FROM avila.invoice i
                JOIN avila.source_file sf ON sf.invoice_id = i.id
                ORDER BY i.invoice_number, sf.created_at
                """
            )
            rows = cur.fetchall()
            # Prefer one path per invoice: packet over supporting over scan.
            by_invoice: dict[str, dict] = {}
            for row in rows:
                current = by_invoice.get(row["invoice_id"])
                rank = {"invoice_packet": 0, "supporting": 1, "needs_page_check": 2}.get(
                    row["file_label"], 3
                )
                if current is None or rank < current["_rank"]:
                    item = dict(row)
                    item["_rank"] = rank
                    by_invoice[row["invoice_id"]] = item

            for invoice_id, row in by_invoice.items():
                path = row["backup_path"]
                name, cedula = extract_titular_from_path(path)
                ocr_text = ""
                path_weak = not name or len(name.split()) < 2
                if path_weak and not cedula:
                    cache = _read_cache(path)
                    if cache and cache.get("pages"):
                        ocr_text = "\n".join(
                            (page.get("text") or "") for page in cache["pages"][:3]
                        )
                        name, cedula = extract_titular_from_ocr(ocr_text)
                if not name and not cedula:
                    # Clear a prior weak/wrong titular so the invoice is not stuck.
                    cur.execute(
                        "DELETE FROM avila.invoice_person WHERE invoice_id = %s AND role = 'titular'",
                        (invoice_id,),
                    )
                    skipped += 1
                    continue
                ensure_invoice_titular(
                    cur,
                    invoice_id,
                    {
                        "path": path,
                        "invoice_number": row["invoice_number"],
                        "label": row["file_label"],
                        "related_invoice_number": "",
                        "invoice_range": "",
                    },
                    ocr_text,
                )
                linked += 1
                if linked % 100 == 0:
                    conn.commit()
                    print(f"linked {linked:,}")
            # Drop orphan provisional persons no longer linked to any invoice.
            cur.execute(
                """
                DELETE FROM avila.person p
                WHERE p.provisional_key IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id
                  )
                """
            )
            conn.commit()
    print(f"Done titular links={linked:,} skipped_no_name={skipped:,}")


if __name__ == "__main__":
    main()
