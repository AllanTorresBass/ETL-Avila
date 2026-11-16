#!/usr/bin/env python3
"""Fix Aaron/Helber identity docs: reclassify false cédulas; upload crop PNG splits.

Keeps full packet pages. Adds dedicated Blob objects for:
  - cedula-HELBER-…png → document_type cedula_identidad
  - carnet-BDV-…png → document_type carnet
Linked to Helber person + primary Aaron invoice (7394 collage source).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import classify_document  # noqa: E402
from env_load import load_env  # noqa: E402
from ocr_invoice_pages import _read_cache, cache_path  # noqa: E402
from upload_documents_to_blob import put_blob  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "output/persons/AARON MATHEUS"
HELBER_ID = "ba69bb1a-bdb6-432b-9f56-77997f975166"
AARON_FACTS = ("7316", "7394", "7759", "7798", "7799", "8322")
PRIMARY_FACT = "7394"

CROPS = (
    {
        "file": DOSSIER / "cedula-HELBER-JOSE-MATHEUS-ANDARA-V13996036.png",
        "document_type": "cedula_identidad",
        "evidence": "crop_cedula_card",
        "page_index": 900,
        "label": "cedula-helber-13996036.png",
    },
    {
        "file": DOSSIER / "carnet-BDV-HELBER-J-MATHEUS-A-13996036.png",
        "document_type": "carnet",
        "evidence": "crop_carnet_bdv",
        "page_index": 901,
        "label": "carnet-helber-bdv-13996036.png",
    },
)


def connect():
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL_UNPOOLED missing")
    return psycopg.connect(url, row_factory=dict_row)


def reclassify_packet_pages(cur) -> dict:
    cur.execute(
        """
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.evidence, sf.backup_path, i.invoice_number
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE i.invoice_number = ANY(%s)
        ORDER BY i.invoice_number, d.page_index
        """,
        (list(AARON_FACTS),),
    )
    docs = cur.fetchall()
    stats = {"scanned": len(docs), "changed": 0, "cedula_kept": 0, "carnet_set": 0}
    for d in docs:
        cache = _read_cache(d["backup_path"]) if cache_path(d["backup_path"]).is_file() else None
        pages = (cache or {}).get("pages") or []
        text = ""
        if 0 < d["page_index"] <= len(pages):
            text = pages[d["page_index"] - 1].get("text") or ""
        new_type, new_ev = classify_document(text, backup_path=d["backup_path"])
        if new_type == d["document_type"] and new_ev == (d["evidence"] or ""):
            if new_type == "cedula_identidad":
                stats["cedula_kept"] += 1
            continue
        if new_type in {"cedula_identidad", "carnet"}:
            person_sql = HELBER_ID
        elif d["document_type"] == "cedula_identidad":
            person_sql = None  # demote false cédula — clear wrong person link
        else:
            person_sql = "KEEP"
        if person_sql == "KEEP":
            cur.execute(
                """
                UPDATE avila.document
                SET document_type = %s::avila.document_type,
                    evidence = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (new_type, new_ev, d["id"]),
            )
        else:
            cur.execute(
                """
                UPDATE avila.document
                SET document_type = %s::avila.document_type,
                    evidence = %s,
                    person_id = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (new_type, new_ev, person_sql, d["id"]),
            )
        stats["changed"] += 1
        if new_type == "cedula_identidad":
            stats["cedula_kept"] += 1
        if new_type == "carnet":
            stats["carnet_set"] += 1
        print(
            f"  {d['invoice_number']} p{d['page_index']}: "
            f"{d['document_type']} → {new_type} ({new_ev})"
        )
    return stats


def ensure_crop_source(cur, invoice_id: str) -> str:
    backup_path = "output/persons/AARON MATHEUS/identity-crops"
    cur.execute("SELECT id FROM avila.source_file WHERE backup_path = %s", (backup_path,))
    row = cur.fetchone()
    if row:
        return str(row["id"])
    cur.execute(
        """
        INSERT INTO avila.source_file (
          invoice_id, backup_path, file_label, rule_id, confidence, extension, pages, bytes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            invoice_id,
            backup_path,
            "identity-crops-helber",
            "manual_identity_crop",
            "high",
            ".png",
            2,
            sum(c["file"].stat().st_size for c in CROPS if c["file"].is_file()),
        ),
    )
    return str(cur.fetchone()["id"])


def upload_crops(cur, invoice_id: str, invoice_number: str, source_id: str) -> list[dict]:
    out = []
    for crop in CROPS:
        path: Path = crop["file"]
        if not path.is_file():
            raise SystemExit(f"Missing crop: {path}")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = f"output/persons/AARON MATHEUS/{path.name}"
        pathname = (
            f"avila/invoices/{invoice_number}/identity-crops/"
            f"{crop['page_index']:03d}-{crop['document_type']}.png"
        )
        blob = put_blob(pathname, path)
        cur.execute(
            """
            INSERT INTO avila.document (
              source_file_id, invoice_id, person_id, page_index, document_type, evidence,
              blob_pathname, blob_url, content_type, byte_size, sha256, upload_status
            ) VALUES (
              %s, %s, %s::uuid, %s, %s::avila.document_type, %s,
              %s, %s, %s, %s, %s, 'uploaded'
            )
            ON CONFLICT (source_file_id, page_index) DO UPDATE SET
              document_type = EXCLUDED.document_type,
              evidence = EXCLUDED.evidence,
              person_id = EXCLUDED.person_id,
              blob_pathname = EXCLUDED.blob_pathname,
              blob_url = EXCLUDED.blob_url,
              content_type = EXCLUDED.content_type,
              byte_size = EXCLUDED.byte_size,
              sha256 = EXCLUDED.sha256,
              upload_status = 'uploaded',
              upload_error = NULL,
              updated_at = now()
            RETURNING id::text, document_type::text, blob_pathname
            """,
            (
                source_id,
                invoice_id,
                HELBER_ID,
                crop["page_index"],
                crop["document_type"],
                crop["evidence"],
                pathname,
                blob.get("url"),
                "image/png",
                path.stat().st_size,
                sha,
            ),
        )
        row = cur.fetchone()
        out.append(dict(row))
        print("uploaded crop", row)
    return out


def main() -> None:
    load_env()
    with connect() as conn:
        with conn.cursor() as cur:
            print("reclassify…")
            print(reclassify_packet_pages(cur))
            cur.execute(
                "SELECT id FROM avila.invoice WHERE invoice_number = %s", (PRIMARY_FACT,)
            )
            inv = cur.fetchone()
            if not inv:
                raise SystemExit(f"Invoice {PRIMARY_FACT} missing")
            invoice_id = str(inv["id"])
            source_id = ensure_crop_source(cur, invoice_id)
            print("upload crops…")
            crops = upload_crops(cur, invoice_id, PRIMARY_FACT, source_id)
            # Ensure Helber owns remaining true cédula/carnet pages
            cur.execute(
                """
                UPDATE avila.document d
                SET person_id = %s::uuid, updated_at = now()
                FROM avila.invoice i
                WHERE d.invoice_id = i.id
                  AND i.invoice_number = ANY(%s)
                  AND d.document_type::text IN ('cedula_identidad', 'carnet')
                """,
                (HELBER_ID, list(AARON_FACTS)),
            )
            print("helber identity pages linked", cur.rowcount)
        conn.commit()
    report = DOSSIER / "identity-load-report.md"
    report.write_text(
        "# Identity crops load\n\n"
        "Full packet pages kept; false `cedula_identidad` labels reclassified.\n\n"
        "Dedicated Blob crops (Helber):\n\n"
        + "\n".join(f"- `{c['document_type']}` → `{c['blob_pathname']}` (`{c['id']}`)" for c in crops)
        + "\n",
        encoding="utf-8",
    )
    print("wrote", report)


if __name__ == "__main__":
    main()
