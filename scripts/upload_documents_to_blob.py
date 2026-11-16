"""Load invoice-universe files into Neon (avila schema) and Vercel Blob.

Reads output/invoices/invoices.csv and OCR cache. One page = one document row
and one Blob object. Prefer a private store: set BLOB_ACCESS=private (default in
blob_put.mjs). Use BLOB_ACCESS=public only for the legacy public store.
Resumes by document.upload_status / blob_pathname.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    account_code_from_label,
    classify_document,
    extract_identity_number,
    extract_name_from_cedula_ocr,
    extract_titular_from_ocr,
    extract_titular_from_path,
)
from env_load import load_env
from ocr_invoice_pages import (
    BACKUP,
    CACHE_DIR,
    INVENTORY,
    _read_cache,
    _render_office,
    _render_pdf,
    cache_path,
)

ROOT = Path(__file__).resolve().parents[1]
BLOB_PUT = ROOT / "scripts" / "blob_put.mjs"
TARGET_LABELS = {"invoice_packet", "supporting", "needs_page_check"}


def connect():
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    for key in ("BLOB_READ_WRITE_TOKEN", "BLOB_STORE_ID", "BLOB_ACCESS", "PATH"):
        if key in env and env[key]:
            os.environ[key] = env[key]
    os.environ.setdefault("BLOB_ACCESS", "private")
    if "BLOB_READ_WRITE_TOKEN" not in os.environ and env.get("BLOB_READ_WRITE_TOKEN"):
        os.environ["BLOB_READ_WRITE_TOKEN"] = env["BLOB_READ_WRITE_TOKEN"]
    # Prefer Homebrew tools for render
    os.environ["PATH"] = f"/opt/homebrew/bin:{os.environ.get('PATH', '')}"
    return psycopg.connect(url, row_factory=dict_row)


def invoice_key(row: dict) -> str:
    if row.get("invoice_number"):
        return row["invoice_number"]
    if row.get("related_invoice_number") and row["label"] == "supporting":
        return row["related_invoice_number"]
    if row.get("invoice_range"):
        return f"range:{row['invoice_range'].replace(';', '_')}"
    digest = hashlib.sha256(row["path"].encode("utf-8")).hexdigest()[:16]
    return f"path:{digest}"


def source_sha(relative: str) -> str:
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]


def blob_pathname(invoice_number: str, relative: str, page_index: int, document_type: str) -> str:
    safe_inv = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in invoice_number)[:80]
    return f"avila/invoices/{safe_inv}/{source_sha(relative)}/{page_index:03d}-{document_type}.png"


def put_blob(pathname: str, file_path: Path) -> dict:
    env = os.environ.copy()
    env.update({k: v for k, v in load_env().items() if k.startswith("BLOB")})
    proc = subprocess.run(
        ["node", str(BLOB_PUT), pathname, str(file_path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "blob_put failed")[:300])
    return json.loads(proc.stdout)


def ensure_account(cur, label: str):
    code = account_code_from_label(label)
    if not code:
        return None
    cur.execute("SELECT id FROM avila.account WHERE code = %s", (code,))
    row = cur.fetchone()
    return row["id"] if row else None


def upsert_titular_person(
    cur, *, full_name: str | None, identity_number: str | None, invoice_number: str
) -> str | None:
    """Each invoice has one titular person (the client)."""
    if not full_name and not identity_number:
        return None
    if identity_number:
        cur.execute(
            """
            INSERT INTO avila.person (identity_type, identity_number, full_name)
            VALUES ('cedula'::avila.identity_type, %s, %s)
            ON CONFLICT (identity_type, identity_number) DO UPDATE
              SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), avila.person.full_name),
                  updated_at = now()
            RETURNING id
            """,
            (identity_number, full_name),
        )
        return cur.fetchone()["id"]
    key = f"titular:{invoice_number}:{fold_name(full_name or '')}"
    cur.execute(
        """
        INSERT INTO avila.person (identity_type, full_name, provisional_key)
        VALUES ('unknown'::avila.identity_type, %s, %s)
        ON CONFLICT (provisional_key) DO UPDATE
          SET full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), avila.person.full_name),
              updated_at = now()
        RETURNING id
        """,
        (full_name, key),
    )
    return cur.fetchone()["id"]


def fold_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def ensure_invoice_titular(cur, invoice_id: str, row: dict, ocr_text: str = "") -> str | None:
    name, cedula = extract_titular_from_path(row.get("path") or "")
    path_weak = not name or len(name.split()) < 2
    if (path_weak and not cedula) and ocr_text:
        ocr_name, ocr_cedula = extract_titular_from_ocr(ocr_text)
        if ocr_name or ocr_cedula:
            name, cedula = ocr_name or name, ocr_cedula or cedula
    person_id = upsert_titular_person(
        cur,
        full_name=name,
        identity_number=cedula,
        invoice_number=invoice_key(row),
    )
    if person_id:
        # One titular per invoice: drop prior titular links before writing this one.
        cur.execute(
            "DELETE FROM avila.invoice_person WHERE invoice_id = %s AND role = 'titular'",
            (invoice_id,),
        )
        link_invoice_person(cur, invoice_id, person_id, "titular")
    return person_id


def upsert_invoice(cur, row: dict) -> str:
    number = invoice_key(row)
    account_id = ensure_account(cur, row.get("account") or "")
    cur.execute(
        """
        INSERT INTO avila.invoice (
          invoice_number, account_id, invoice_range, year, month, lote, workflow, channel, duplicate_group
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (invoice_number) DO UPDATE SET
          account_id = COALESCE(EXCLUDED.account_id, avila.invoice.account_id),
          invoice_range = COALESCE(NULLIF(EXCLUDED.invoice_range, ''), avila.invoice.invoice_range),
          year = COALESCE(NULLIF(EXCLUDED.year, ''), avila.invoice.year),
          month = COALESCE(NULLIF(EXCLUDED.month, ''), avila.invoice.month),
          lote = COALESCE(NULLIF(EXCLUDED.lote, ''), avila.invoice.lote),
          workflow = COALESCE(NULLIF(EXCLUDED.workflow, ''), avila.invoice.workflow),
          channel = COALESCE(NULLIF(EXCLUDED.channel, ''), avila.invoice.channel),
          duplicate_group = COALESCE(NULLIF(EXCLUDED.duplicate_group, ''), avila.invoice.duplicate_group)
        RETURNING id
        """,
        (
            number,
            account_id,
            row.get("invoice_range") or None,
            row.get("year") or None,
            row.get("month") or None,
            row.get("lote") or None,
            row.get("workflow") or None,
            row.get("channel") or None,
            row.get("duplicate_group") or None,
        ),
    )
    invoice_id = cur.fetchone()["id"]
    ensure_invoice_titular(cur, invoice_id, row)
    return invoice_id


def upsert_source_file(cur, row: dict, invoice_id: str | None) -> str:
    pages = int(row["pages"]) if row.get("pages") and str(row["pages"]).isdigit() else None
    bytes_ = int(row["bytes"]) if row.get("bytes") and str(row["bytes"]).isdigit() else None
    cur.execute(
        """
        INSERT INTO avila.source_file (
          invoice_id, backup_path, file_label, rule_id, confidence, extension, pages, bytes,
          duplicate_group, related_invoice_number, account_raw
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (backup_path) DO UPDATE SET
          invoice_id = COALESCE(EXCLUDED.invoice_id, avila.source_file.invoice_id),
          file_label = EXCLUDED.file_label,
          rule_id = EXCLUDED.rule_id,
          pages = COALESCE(EXCLUDED.pages, avila.source_file.pages),
          bytes = COALESCE(EXCLUDED.bytes, avila.source_file.bytes)
        RETURNING id
        """,
        (
            invoice_id,
            row["path"],
            row["label"],
            row.get("rule_id") or None,
            row.get("confidence") or None,
            row.get("extension") or None,
            pages,
            bytes_,
            row.get("duplicate_group") or None,
            row.get("related_invoice_number") or None,
            row.get("account_raw") or None,
        ),
    )
    return cur.fetchone()["id"]


def upsert_person_from_text(cur, text: str) -> str | None:
    found = extract_identity_number(text)
    if not found:
        return None
    identity_type, identity_number = found
    full_name = extract_name_from_cedula_ocr(text)
    cur.execute(
        """
        INSERT INTO avila.person (identity_type, identity_number, full_name)
        VALUES (%s::avila.identity_type, %s, %s)
        ON CONFLICT (identity_type, identity_number) DO UPDATE SET
          full_name = coalesce(EXCLUDED.full_name, avila.person.full_name),
          updated_at = now()
        RETURNING id
        """,
        (identity_type, identity_number, full_name),
    )
    person_id = cur.fetchone()["id"]
    if full_name:
        # Absorb provisional same-name rows into this CI person.
        cur.execute(
            """
            SELECT id FROM avila.person
            WHERE id <> %s
              AND identity_number IS NULL
              AND provisional_key IS NOT NULL
              AND lower(full_name) = lower(%s)
            """,
            (person_id, full_name),
        )
        for orphan in cur.fetchall():
            cur.execute(
                """
                UPDATE avila.invoice_person SET person_id = %s
                WHERE person_id = %s
                  AND NOT EXISTS (
                    SELECT 1 FROM avila.invoice_person x
                    WHERE x.invoice_id = avila.invoice_person.invoice_id
                      AND x.person_id = %s
                  )
                """,
                (person_id, orphan["id"], person_id),
            )
            cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s", (orphan["id"],))
            cur.execute(
                "UPDATE avila.document SET person_id = %s WHERE person_id = %s",
                (person_id, orphan["id"]),
            )
            cur.execute("DELETE FROM avila.person WHERE id = %s", (orphan["id"],))
    return person_id


def _titular_ci_for_invoice(cur, invoice_id: str) -> str | None:
    cur.execute(
        """
        SELECT p.identity_number
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = %s AND ip.role = 'titular'
        LIMIT 1
        """,
        (invoice_id,),
    )
    row = cur.fetchone()
    return row["identity_number"] if row else None


def link_invoice_person(cur, invoice_id: str, person_id: str, role: str = "unknown") -> None:
    # Upgrade unknown → beneficiario when a titular already exists with a different CI.
    if role == "unknown":
        cur.execute(
            "SELECT identity_number FROM avila.person WHERE id = %s",
            (person_id,),
        )
        pers = cur.fetchone()
        titular_ci = _titular_ci_for_invoice(cur, invoice_id)
        if pers and pers.get("identity_number") and titular_ci:
            if pers["identity_number"] == titular_ci:
                role = "titular"
            else:
                role = "beneficiario"
        elif pers and pers.get("identity_number") and not titular_ci:
            role = "titular"
    cur.execute(
        """
        INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
        VALUES (%s, %s, %s::avila.invoice_person_role, 'ocr')
        ON CONFLICT (invoice_id, person_id) DO UPDATE
          SET role = CASE
            WHEN EXCLUDED.role = 'titular' THEN 'titular'::avila.invoice_person_role
            WHEN avila.invoice_person.role = 'unknown'
              AND EXCLUDED.role IN ('beneficiario', 'titular')
              THEN EXCLUDED.role
            ELSE avila.invoice_person.role
          END,
          source = coalesce(avila.invoice_person.source, EXCLUDED.source)
        """,
        (invoice_id, person_id, role),
    )


def render_pages(relative: str) -> tuple[list[Path | None], str, tempfile.TemporaryDirectory | None]:
    source = BACKUP / relative
    if not source.is_file():
        return [], "missing", None
    suffix = source.suffix.lower()
    tmp = tempfile.TemporaryDirectory(prefix="avila-upload-")
    folder = Path(tmp.name)
    if suffix == ".pdf":
        images, error = _render_pdf(source, folder)
        return images, error, tmp
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return [source], "", tmp
    if suffix in {".pptx", ".potx"}:
        images, error = _render_office(source, folder)
        return images, error, tmp
    return [], f"unsupported:{suffix}", tmp


def load_inventory(limit: int = 0, paths: list[str] | None = None) -> list[dict]:
    rows = []
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["label"] not in TARGET_LABELS:
                continue
            if paths and row["path"] not in paths:
                continue
            rows.append(row)
            if limit and not paths and len(rows) >= limit:
                break
    return rows


def process_file(conn, row: dict, *, upload: bool, metadata_only: bool = False) -> dict:
    stats = {"pages": 0, "uploaded": 0, "failed": 0, "skipped": 0}
    relative = row["path"]
    with conn.cursor() as cur:
        invoice_id = upsert_invoice(cur, row)
        source_id = upsert_source_file(cur, row, invoice_id)
        conn.commit()
        if metadata_only:
            cur.execute(
                """
                SELECT count(*)::int AS n,
                       count(*) FILTER (WHERE upload_status = 'uploaded')::int AS up
                FROM avila.document WHERE source_file_id = %s
                """,
                (source_id,),
            )
            counts = cur.fetchone()
            if counts and counts["n"] > 0 and counts["n"] == counts["up"]:
                # Person/titular already refreshed via upsert_invoice; skip re-render.
                stats["skipped"] += counts["n"]
                return stats

    cache = _read_cache(relative) if cache_path(relative).is_file() else None
    images, render_error, tmp = render_pages(relative)
    try:
        if render_error and not images:
            page_text = ""
            page_error = render_error
            dtype, evidence = classify_document(page_text, backup_path=relative, page_error=page_error)
            _upsert_document(
                conn,
                source_id=source_id,
                invoice_id=invoice_id,
                page_index=1,
                document_type=dtype,
                evidence=evidence,
                image=None,
                text="",
                upload=upload,
                stats=stats,
            )
            return stats

        # Prefer cache page count when render failed mid-way
        page_records = (cache or {}).get("pages") or []
        total = max(len(images), len(page_records), 1)
        for index in range(1, total + 1):
            image = images[index - 1] if index <= len(images) else None
            cached = page_records[index - 1] if index <= len(page_records) else {}
            text = cached.get("text") or ""
            page_error = cached.get("error") or ("" if image else "no_slide_image")
            dtype, evidence = classify_document(
                text, backup_path=relative, page_error=page_error
            )
            _upsert_document(
                conn,
                source_id=source_id,
                invoice_id=invoice_id,
                page_index=index,
                document_type=dtype,
                evidence=evidence,
                image=image,
                text=text,
                upload=upload,
                stats=stats,
            )
    finally:
        if tmp is not None:
            tmp.cleanup()
    return stats


def _upsert_document(
    conn,
    *,
    source_id: str,
    invoice_id: str,
    page_index: int,
    document_type: str,
    evidence: str,
    image: Path | None,
    text: str,
    upload: bool,
    stats: dict,
) -> None:
    stats["pages"] += 1
    person_id = None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT backup_path FROM avila.source_file WHERE id = %s", (source_id,)
        )
        relative = cur.fetchone()["backup_path"]
        cur.execute(
            "SELECT invoice_number FROM avila.invoice WHERE id = %s", (invoice_id,)
        )
        inv_number = cur.fetchone()["invoice_number"]

        if document_type in {"cedula_identidad", "pasaporte"} and text:
            person_id = upsert_person_from_text(cur, text)
            if person_id:
                # Cédula page may be the titular or the beneficiary; keep role unknown
                # unless this person is already linked as titular.
                link_invoice_person(cur, invoice_id, person_id, "unknown")
        if document_type == "factura_fiscal" and text:
            ensure_invoice_titular(
                cur,
                invoice_id,
                {
                    "path": relative,
                    "invoice_number": inv_number,
                    "label": "",
                    "related_invoice_number": "",
                    "invoice_range": "",
                },
                text,
            )

        pathname = blob_pathname(inv_number, relative, page_index, document_type)

        cur.execute(
            """
            INSERT INTO avila.document (
              source_file_id, invoice_id, person_id, page_index, document_type, evidence,
              blob_pathname, upload_status
            ) VALUES (%s,%s,%s,%s,%s::avila.document_type,%s,%s,'pending')
            ON CONFLICT (source_file_id, page_index) DO UPDATE SET
              document_type = EXCLUDED.document_type,
              evidence = EXCLUDED.evidence,
              person_id = COALESCE(EXCLUDED.person_id, avila.document.person_id),
              updated_at = now()
            RETURNING id, upload_status, blob_url
            """,
            (source_id, invoice_id, person_id, page_index, document_type, evidence, pathname),
        )
        doc = cur.fetchone()
        conn.commit()
        doc_id = doc["id"]

        if not upload:
            stats["skipped"] += 1
            return
        if doc["upload_status"] == "uploaded" and doc.get("blob_url"):
            stats["skipped"] += 1
            return
        if image is None or not Path(image).is_file():
            cur.execute(
                """
                UPDATE avila.document
                SET upload_status = 'failed', upload_error = %s, updated_at = now()
                WHERE id = %s
                """,
                ("no_image", doc_id),
            )
            conn.commit()
            stats["failed"] += 1
            return
        try:
            blob = put_blob(pathname, Path(image))
            sha = hashlib.sha256(Path(image).read_bytes()).hexdigest()
            cur.execute(
                """
                UPDATE avila.document SET
                  blob_pathname = %s,
                  blob_url = %s,
                  content_type = %s,
                  byte_size = %s,
                  sha256 = %s,
                  upload_status = 'uploaded',
                  upload_error = NULL,
                  updated_at = now()
                WHERE id = %s
                """,
                (
                    blob.get("pathname") or pathname,
                    blob["url"],
                    blob.get("contentType"),
                    Path(image).stat().st_size,
                    sha,
                    doc_id,
                ),
            )
            conn.commit()
            stats["uploaded"] += 1
        except Exception as exc:  # noqa: BLE001
            cur.execute(
                """
                UPDATE avila.document
                SET upload_status = 'failed', upload_error = %s, updated_at = now()
                WHERE id = %s
                """,
                (str(exc)[:300], doc_id),
            )
            conn.commit()
            stats["failed"] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Load documents into Neon + Vercel Blob")
    parser.add_argument("--limit", type=int, default=0, help="Max source files to process")
    parser.add_argument("--paths-file", type=str, default="", help="Newline-separated backup paths")
    parser.add_argument("--no-upload", action="store_true", help="Insert DB rows without Blob put")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip re-render/Blob when all pages for a file are already uploaded",
    )
    parser.add_argument("--install-blob", action="store_true", help="npm install @vercel/blob in scripts/")
    args = parser.parse_args()

    if args.install_blob:
        subprocess.run(
            ["npm", "install", "@vercel/blob", "--no-fund", "--no-audit"],
            cwd=ROOT / "scripts",
            check=True,
        )

    paths = None
    if args.paths_file:
        paths = [
            line.strip()
            for line in Path(args.paths_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    rows = load_inventory(limit=args.limit, paths=paths)
    print(f"Files to process: {len(rows):,}")
    conn = connect()
    totals = {"pages": 0, "uploaded": 0, "failed": 0, "skipped": 0}
    try:
        for index, row in enumerate(rows, start=1):
            stats = process_file(
                conn,
                row,
                upload=not args.no_upload,
                metadata_only=args.metadata_only,
            )
            for key in totals:
                totals[key] += stats[key]
            if index % 10 == 0 or index == len(rows):
                print(
                    f"File {index:,}/{len(rows):,} pages={totals['pages']:,} "
                    f"uploaded={totals['uploaded']:,} failed={totals['failed']:,} "
                    f"skipped={totals['skipped']:,}"
                )
    finally:
        conn.close()
    print("Done", totals)


if __name__ == "__main__":
    main()
