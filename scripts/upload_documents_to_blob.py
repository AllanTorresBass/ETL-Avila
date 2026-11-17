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
import zlib
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    account_code_from_label,
    classify_document,
    extract_all_cedulas,
    extract_name_from_cedula_ocr,
    extract_personal_identity,
    extract_titular_from_ocr,
    extract_titular_from_path,
)
from person_upsert import fold_person_name, upsert_by_ci, upsert_by_name, upsert_titular
from env_load import load_env
import provenance
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
# Pages whose CI may become the invoice titular. An acta names the child, so it never qualifies.
CI_TITULAR_TYPES = frozenset({"cedula_identidad", "pasaporte", "carnet", "documentos_identificacion"})


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
    """Each invoice has one titular person (the client). invoice_number kept for API compat."""
    _ = invoice_number
    return upsert_titular(cur, full_name=full_name, identity_number=identity_number)


def _names_refer_to_same_person(a: str | None, b: str | None) -> bool:
    """True when the shorter folded token set is contained in the longer (min 2 tokens)."""
    fa = set(fold_person_name(a or "").split())
    fb = set(fold_person_name(b or "").split())
    if len(fa) < 2 or len(fb) < 2:
        return False
    shorter, longer = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    return shorter <= longer


def _link_path_name_as_beneficiario(
    cur, invoice_id: str, name: str, titular_id: str, path_ci: str | None = None
) -> str | None:
    """When the FACT path names a patient different from the CI titular.

    Skips (returns None) when the path could be the titular themself: same CI,
    name subset match, or a titular with no name to compare against — a nameless
    CI row plus a path name would otherwise split one person into two.
    """
    cur.execute(
        "SELECT full_name, identity_number FROM avila.person WHERE id = %s::uuid",
        (titular_id,),
    )
    titular = cur.fetchone()
    if not titular:
        return None
    titular_ci = titular.get("identity_number")
    if path_ci and titular_ci and path_ci == titular_ci:
        return None
    if not path_ci and not (titular.get("full_name") or "").strip():
        return None
    if _names_refer_to_same_person(name, titular.get("full_name")):
        return None
    if path_ci:
        path_person_id, _ = upsert_by_ci(
            cur, identity_number=path_ci, full_name=name, identity_type="cedula"
        )
    else:
        path_person_id, _ = upsert_by_name(cur, full_name=name)
    if not path_person_id or str(path_person_id) == str(titular_id):
        return None
    link_invoice_person(
        cur, invoice_id, path_person_id, "beneficiario", source="path", rule_id="path_beneficiario"
    )
    return str(path_person_id)


def _role_of(cur, invoice_id: str, person_id: str) -> str | None:
    cur.execute(
        "SELECT role::text AS role FROM avila.invoice_person WHERE invoice_id = %s AND person_id = %s::uuid",
        (invoice_id, person_id),
    )
    row = cur.fetchone()
    return row["role"] if row else None


def record_role(
    cur,
    invoice_id: str,
    person_id: str,
    old_role: str | None,
    *,
    rule_id: str,
    reason: str | None = None,
    confidence: float | None = None,
) -> None:
    provenance.record(
        cur,
        entity="invoice_person",
        entity_id=f"{invoice_id}:{person_id}",
        field="role",
        old=old_role,
        new=_role_of(cur, invoice_id, person_id),
        rule_id=rule_id,
        reason=reason,
        confidence=confidence,
    )


def promote_ci_person_as_titular(
    cur, invoice_id: str, person_id: str, *, source: str = "ocr_cedula"
) -> None:
    """Cédula/carnet CI wins: that person becomes titular; prior path titular → beneficiario."""
    cur.execute(
        """
        UPDATE avila.invoice_person
        SET role = 'beneficiario',
            source = CASE WHEN source = 'legacy_unknown' THEN 'path' ELSE source END
        WHERE invoice_id = %s
          AND role = 'titular'
          AND person_id <> %s::uuid
        RETURNING person_id
        """,
        (invoice_id, person_id),
    )
    for demoted in cur.fetchall():
        provenance.record(
            cur,
            entity="invoice_person",
            entity_id=f"{invoice_id}:{demoted['person_id']}",
            field="role",
            old="titular",
            new="beneficiario",
            rule_id="ci_titular_demotes_previous",
        )
    link_invoice_person(
        cur, invoice_id, person_id, "titular", source=source, rule_id="ci_titular_promotion"
    )
    cur.execute(
        """
        UPDATE avila.invoice_person
        SET source = %s
        WHERE invoice_id = %s AND person_id = %s::uuid
        """,
        (source, invoice_id, person_id),
    )


def titular_promotion_blocker(cur, invoice_id: str, person_id: str) -> str | None:
    """Why this CI person must NOT replace the invoice's current titular, or None.

    - ``workbook_titular``: a workbook titular with CI / phone / DOB is protected.
    - ``ci_conflict``: another plastic-ID CI is already titular — two insured
      candidates on one packet need a human decision (skill: stop / escalate).
    """
    cur.execute(
        "SELECT identity_number FROM avila.person WHERE id = %s::uuid", (person_id,)
    )
    new = cur.fetchone()
    new_ci = new.get("identity_number") if new else None
    cur.execute(
        """
        SELECT ip.source, p.identity_number, p.phone, p.birth_date
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = %s AND ip.role = 'titular' AND ip.person_id <> %s::uuid
        """,
        (invoice_id, person_id),
    )
    for row in cur.fetchall():
        if row.get("source") == "workbook" and (
            row.get("identity_number") or row.get("phone") or row.get("birth_date")
        ):
            return "workbook_titular"
        if (
            row.get("source") == "ocr_cedula"
            and row.get("identity_number")
            and row["identity_number"] != new_ci
        ):
            return "ci_conflict"
    return None


def try_promote_ci_titular(
    cur,
    invoice_id: str,
    person_id: str,
    *,
    path_name: str | None = None,
    path_ci: str | None = None,
    source: str = "ocr_cedula",
) -> str:
    """Single entry point for "plastic ID CI → titular" (loader, reclassify, repair).

    Returns ``"promoted"`` or the blocker reason. When blocked nothing on the
    invoice changes and a review item is opened.
    """
    reason = titular_promotion_blocker(cur, invoice_id, person_id)
    if reason:
        provenance.open_review(
            cur,
            kind=reason,
            dedupe_key=f"{reason}:{invoice_id}:{person_id}",
            person_id=person_id,
            invoice_id=invoice_id,
            evidence={"blocked_rule": "ci_titular_promotion"},
        )
        return reason
    promote_ci_person_as_titular(cur, invoice_id, person_id, source=source)
    if path_name:
        _link_path_name_as_beneficiario(cur, invoice_id, path_name, person_id, path_ci)
    return "promoted"


def identity_page_ci(text: str, prefer: str | None = None) -> tuple[str | None, str]:
    """Pick the single personal CI on an identity page.

    Returns (ci, status) with status ``ok`` / ``none`` / ``multiple``. A RIF never
    counts (provider letterhead on a weak collage OCR). Collages often mount the
    titular's and the patient's cards together: when ``prefer`` (the invoice's
    current titular CI) is among them it is the clear insured; otherwise the
    page is ambiguous and must be reviewed.
    """
    found = extract_all_cedulas(text)
    if len(found) > 1:
        if prefer and prefer in found:
            return prefer, "ok"
        return None, "multiple"
    if found:
        return found[0], "ok"
    personal = extract_personal_identity(text)
    if personal and personal[0] == "cedula":
        return personal[1], "ok"
    return None, "none"


_SCAN_PACKET_PATHS: set[str] = set()


def _path_titular(relative: str) -> tuple[str | None, str | None]:
    """Scanner images (IMG_0001 under a lot folder) carry no person in the path."""
    if relative in _SCAN_PACKET_PATHS:
        return None, None
    return extract_titular_from_path(relative)


def ensure_invoice_titular(cur, invoice_id: str, row: dict, ocr_text: str = "") -> str | None:
    # Protect workbook-enriched titulars with CI / contact from weak path overwrites.
    cur.execute(
        """
        SELECT ip.source, p.identity_number, p.phone, p.birth_date, p.id AS person_id
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = %s AND ip.role = 'titular'
        LIMIT 1
        """,
        (invoice_id,),
    )
    existing = cur.fetchone()

    if (row.get("path") or "") in _SCAN_PACKET_PATHS:
        # Roles for scan packets come from fiscal_extract + identity pages only.
        return str(existing["person_id"]) if existing else None
    name, cedula = _path_titular(row.get("path") or "")
    path_weak = not name or len(name.split()) < 2
    if (path_weak and not cedula) and ocr_text:
        ocr_name, ocr_cedula = extract_titular_from_ocr(ocr_text)
        if ocr_name or ocr_cedula:
            name, cedula = ocr_name or name, ocr_cedula or cedula

    # CI titular (from cédula OCR or workbook) always beats a path-only name.
    if existing and existing.get("identity_number") and not cedula:
        if name:
            _link_path_name_as_beneficiario(
                cur, invoice_id, name, str(existing["person_id"])
            )
        return str(existing["person_id"])

    if existing and existing.get("source") == "workbook":
        has_strength = bool(
            existing.get("identity_number")
            or existing.get("phone")
            or existing.get("birth_date")
        )
        if has_strength:
            # Only upgrade when path/OCR brings a new CI for the same link target.
            if not cedula or (
                existing.get("identity_number") and cedula == existing["identity_number"]
            ):
                return str(existing["person_id"])
            if existing.get("identity_number") and cedula != existing["identity_number"]:
                # Different CI from path — keep workbook person; do not swap.
                return str(existing["person_id"])

    if not name and not cedula:
        # Do not delete an existing titular when path/OCR yields nothing.
        return str(existing["person_id"]) if existing else None

    # Path has a CI: that person is titular.
    if cedula:
        person_id = upsert_titular_person(
            cur,
            full_name=name,
            identity_number=cedula,
            invoice_number=invoice_key(row),
        )
        if not person_id:
            return None
        outcome = try_promote_ci_titular(cur, invoice_id, person_id)
        if outcome == "ci_conflict" and existing:
            # A plastic-ID CI already holds the invoice: the path CI is the
            # patient (adult beneficiario), not the insured.
            link_invoice_person(
                cur, invoice_id, person_id, "beneficiario", source="path", rule_id="path_ci_adult_beneficiario"
            )
            return str(existing["person_id"])
        if outcome != "promoted":
            return str(existing["person_id"]) if existing else None
        return person_id

    # Path name only — provisional titular until a cédula page promotes a CI person.
    person_id = upsert_titular_person(
        cur,
        full_name=name,
        identity_number=None,
        invoice_number=invoice_key(row),
    )
    if person_id:
        if existing and existing.get("identity_number"):
            # Should have returned earlier; keep CI titular.
            _link_path_name_as_beneficiario(cur, invoice_id, name, str(existing["person_id"]))
            return str(existing["person_id"])
        cur.execute(
            "DELETE FROM avila.invoice_person WHERE invoice_id = %s AND role = 'titular'",
            (invoice_id,),
        )
        link_invoice_person(
            cur, invoice_id, person_id, "titular", source="path", rule_id="path_name_titular"
        )
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


_RASTER_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def infer_source_pages(row: dict) -> int | None:
    """Page count for source_file. Inventory often leaves scanner rasters blank."""
    raw = row.get("pages")
    if raw is not None and str(raw).strip().isdigit():
        return int(str(raw).strip())
    ext = (row.get("extension") or Path(row.get("path") or "").suffix or "").lower()
    if ext in _RASTER_EXT:
        return 1
    path = row.get("path") or ""
    if path and cache_path(path).is_file():
        cache = _read_cache(path) or {}
        n = len(cache.get("pages") or [])
        if n:
            return n
    return None


def upsert_source_file(cur, row: dict, invoice_id: str | None) -> str:
    pages = infer_source_pages(row)
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


def _report_titular_review(
    stats: dict,
    invoice_number: str,
    page_index: int,
    reason: str,
    *,
    cur=None,
    invoice_id: str | None = None,
    person_id: str | None = None,
) -> None:
    """Count + queue an invoice that needs a human titular decision (no PHI printed)."""
    stats["titular_review"] = stats.get("titular_review", 0) + 1
    print(f"  titular review: FACT {invoice_number} p{page_index} → {reason}")
    if cur is not None and invoice_id and reason in provenance.REVIEW_KINDS:
        provenance.open_review(
            cur,
            kind=reason,
            dedupe_key=f"{reason}:{invoice_id}:{person_id or page_index}",
            person_id=person_id,
            invoice_id=invoice_id,
            evidence={"page_index": page_index},
        )


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


def link_invoice_person(
    cur,
    invoice_id: str,
    person_id: str,
    role: str = "unknown",
    *,
    source: str = "ocr",
    rule_id: str = "link_invoice_person",
    parentesco: str | None = None,
) -> None:
    old_role = _role_of(cur, invoice_id, person_id)
    _link_invoice_person(cur, invoice_id, person_id, role, source)
    if parentesco:
        cur.execute(
            """
            UPDATE avila.invoice_person SET parentesco = coalesce(parentesco, %s)
            WHERE invoice_id = %s AND person_id = %s::uuid
            """,
            (parentesco, invoice_id, person_id),
        )
    record_role(cur, invoice_id, person_id, old_role, rule_id=rule_id)


def _link_invoice_person(cur, invoice_id: str, person_id: str, role: str, source: str) -> None:
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
        VALUES (%s, %s, %s::avila.invoice_person_role, %s)
        ON CONFLICT (invoice_id, person_id) DO UPDATE
          SET role = CASE
            WHEN EXCLUDED.role = 'titular' THEN 'titular'::avila.invoice_person_role
            WHEN avila.invoice_person.role = 'unknown'
              AND EXCLUDED.role IN ('beneficiario', 'titular')
              THEN EXCLUDED.role
            ELSE avila.invoice_person.role
          END,
          source = CASE
            WHEN avila.invoice_person.source = 'legacy_unknown' THEN EXCLUDED.source
            ELSE avila.invoice_person.source
          END
        """,
        (invoice_id, person_id, role, source),
    )


def render_pages(relative: str) -> tuple[list[Path | None], str, tempfile.TemporaryDirectory | None]:
    source = BACKUP / relative
    if not source.is_file():
        return [], "missing", None
    suffix = source.suffix.lower()
    tmp = tempfile.TemporaryDirectory(prefix="avila-upload-")
    folder = Path(tmp.name)
    with source.open("rb") as handle:
        magic = handle.read(8)
    if magic.startswith((b"\xff\xd8\xff", b"\x89PNG")):
        return [source], "", tmp
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


def process_file(
    conn, row: dict, *, upload: bool, metadata_only: bool = False, invoice_id: str | None = None
) -> dict:
    """Load one backup file. Pass ``invoice_id`` when the caller already upserted the invoice."""
    stats = {"pages": 0, "uploaded": 0, "failed": 0, "skipped": 0}
    relative = row["path"]
    inv_number = invoice_key(row)
    with conn.cursor() as cur, provenance.source("path", relative):
        if invoice_id is None:
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
                relative=relative,
                inv_number=inv_number,
                page_index=1,
                document_type=dtype,
                evidence=evidence,
                image=None,
                text="",
                upload=upload,
                stats=stats,
            )
            _sync_source_pages(conn, source_id, stats["pages"])
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
            with provenance.source("ocr", f"{relative}#{index}"):
                _upsert_document(
                    conn,
                    source_id=source_id,
                    invoice_id=invoice_id,
                    relative=relative,
                    inv_number=inv_number,
                    page_index=index,
                    document_type=dtype,
                    evidence=evidence,
                    image=image,
                    text=text,
                    upload=upload,
                    stats=stats,
                )
        _sync_source_pages(conn, source_id, stats["pages"])
    finally:
        if tmp is not None:
            tmp.cleanup()
    return stats


def _sync_source_pages(conn, source_id: str, page_count: int) -> None:
    """Inventory often omits pages for scanner rasters; persist the rendered count."""
    if page_count <= 0:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE avila.source_file
            SET pages = COALESCE(pages, %s)
            WHERE id = %s AND (pages IS NULL OR pages < %s)
            """,
            (page_count, source_id, page_count),
        )
        conn.commit()


def _upsert_document(
    conn,
    *,
    source_id: str,
    invoice_id: str,
    relative: str,
    inv_number: str,
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
        if document_type in CI_TITULAR_TYPES and text:
            ci, ci_status = identity_page_ci(text, _titular_ci_for_invoice(cur, invoice_id))
            if ci_status == "multiple":
                _report_titular_review(
                    stats, inv_number, page_index, "multiple_ci", cur=cur, invoice_id=invoice_id
                )
            elif ci:
                person_id, _ = upsert_by_ci(
                    cur,
                    identity_number=ci,
                    full_name=extract_name_from_cedula_ocr(text),
                    identity_type="cedula",
                )
            elif document_type == "pasaporte":
                personal = extract_personal_identity(text)
                if personal and personal[0] == "pasaporte":
                    person_id, _ = upsert_by_ci(
                        cur, identity_number=personal[1], identity_type="pasaporte"
                    )
            if person_id:
                # Plastic ID / carnet / ID collage CI is the insurer titular;
                # path patient name (FACT … NAME) → beneficiario when different.
                path_name, path_ci = _path_titular(relative)
                outcome = try_promote_ci_titular(
                    cur, invoice_id, person_id, path_name=path_name, path_ci=path_ci
                )
                if outcome != "promoted":
                    _report_titular_review(
                        stats, inv_number, page_index, outcome,
                        cur=cur, invoice_id=invoice_id, person_id=person_id,
                    )
        elif document_type == "acta_nacimiento" and text:
            # Birth certificate names the child (path patient), not a new titular.
            path_name, _path_ci = _path_titular(relative)
            if path_name:
                person_id, _ = upsert_by_name(cur, full_name=path_name)
                if person_id:
                    link_invoice_person(
                        cur, invoice_id, person_id, "beneficiario",
                        source="path", rule_id="acta_path_beneficiario",
                    )
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
            WITH prior AS (
              SELECT document_type::text AS document_type FROM avila.document
              WHERE source_file_id = %s AND page_index = %s
            )
            INSERT INTO avila.document (
              source_file_id, invoice_id, person_id, page_index, document_type, evidence,
              blob_pathname, upload_status
            ) VALUES (%s,%s,%s,%s,%s::avila.document_type,%s,%s,'pending')
            ON CONFLICT (source_file_id, page_index) DO UPDATE SET
              document_type = EXCLUDED.document_type,
              evidence = EXCLUDED.evidence,
              person_id = COALESCE(EXCLUDED.person_id, avila.document.person_id),
              updated_at = now()
            RETURNING id, upload_status, blob_url, (SELECT document_type FROM prior) AS prior_type
            """,
            (source_id, page_index, source_id, invoice_id, person_id, page_index, document_type, evidence, pathname),
        )
        doc = cur.fetchone()
        doc_id = doc["id"]
        provenance.record(
            cur,
            entity="document",
            entity_id=doc_id,
            field="document_type",
            old=doc["prior_type"],
            new=document_type,
            rule_id=f"classify:{evidence}"[:80],
            source_kind="ocr" if text else "path",
            source_ref=f"{relative}#{page_index}",
        )
        conn.commit()

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


def _control_index(cur) -> dict[str, list[str]]:
    from fiscal_extract import norm_control

    cur.execute("SELECT invoice_number, control_number FROM avila.invoice WHERE control_number IS NOT NULL")
    index: dict[str, list[str]] = {}
    for r in cur.fetchall():
        key = norm_control(r["control_number"])
        if key:
            index.setdefault(key, []).append(r["invoice_number"])
    return index


def _resolve_packet_invoice(
    cur, packet: dict, control_index: dict[str, list[str]] | None = None
) -> tuple[str | None, str]:
    """Invoice number for a scan packet, or (None, reason)."""
    from fiscal_extract import norm_control

    control = norm_control(packet.get("control_number"))
    number = packet.get("invoice_number") or None
    if number:
        cur.execute("SELECT control_number FROM avila.invoice WHERE invoice_number = %s", (number,))
        hit = cur.fetchone()
        if hit and hit["control_number"] and control and norm_control(hit["control_number"]) != control:
            return None, "control_mismatch"
        return number, "invoice_number"
    if control:
        if control_index is None:
            control_index = _control_index(cur)
        matches = control_index.get(control, [])
        if len(matches) == 1:
            return matches[0], "control_number"
        return None, "control_ambiguous" if matches else "control_unknown"
    return None, "no_key"


def _packet_key(packet: dict) -> str:
    """Shard key: packets that may land on the same invoice share a shard."""
    from fiscal_extract import norm_control

    return packet.get("invoice_number") or norm_control(packet.get("control_number")) or packet["packet_id"]


def load_scan_packets(
    conn,
    packets_csv: Path,
    *,
    min_confidence: float,
    upload: bool,
    limit: int = 0,
    shard: tuple[int, int] | None = None,
) -> dict:
    """Load segmented scanner packets (segment_scan_packets.py) as invoice sources.

    Path/OCR titular guessing is off for these files; roles come from the fiscal
    sheet (fiscal_extract) and identity pages through try_promote_ci_titular. An
    invoice that already exists from a PDF gains the scans as extra source files.
    """
    from fiscal_extract import FiscalFields, extract, link_fiscal_roles, write_invoice_fields

    inventory = {}
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            inventory[row["path"]] = row
    packets = list(csv.DictReader(packets_csv.open(newline="", encoding="utf-8")))
    owners: dict[str, int] = {}
    for packet in packets:
        for ref in packet["page_refs"].split("|"):
            path = ref.rsplit("#", 1)[0]
            owners[path] = owners.get(path, 0) + 1
    totals = {"pages": 0, "uploaded": 0, "failed": 0, "skipped": 0, "titular_review": 0}
    counts: dict[str, int] = {}

    def bump(key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    with conn.cursor() as cur:
        control_index = _control_index(cur)
    conn.commit()
    loaded = 0
    for packet in packets:
        if float(packet["confidence"] or 0) < min_confidence:
            bump("below_confidence")
            continue
        if shard and zlib.crc32(_packet_key(packet).encode()) % shard[1] != shard[0]:
            continue
        try:
            refs = packet["page_refs"].split("|")
            paths = list(dict.fromkeys(ref.rsplit("#", 1)[0] for ref in refs))
            with conn.cursor() as cur:
                if any(owners.get(p, 0) > 1 for p in paths):
                    reason = "file_spans_packets"
                    number = None
                else:
                    number, reason = _resolve_packet_invoice(cur, packet, control_index)
                if not number:
                    bump(f"unresolved:{reason}")
                    provenance.open_review(
                        cur,
                        kind="segment_review",
                        dedupe_key=f"segment_review:{packet['packet_id']}",
                        evidence={"reason": reason, "packet_id": packet["packet_id"], "first_page": refs[0]},
                        score=float(packet["confidence"] or 0),
                    )
                    conn.commit()
                    continue
                cur.execute("SELECT 1 FROM avila.invoice WHERE invoice_number = %s", (number,))
                bump("attached_to_existing" if cur.fetchone() else "new_invoice")
            bump(f"resolved_by:{reason}")
            rows = []
            for path in paths:
                base = inventory.get(path)
                if not base:
                    bump("missing_inventory_row")
                    continue
                _SCAN_PACKET_PATHS.add(path)
                rows.append({
                    **base,
                    "invoice_number": number,
                    "related_invoice_number": number,
                    "label": "invoice_packet",
                    "rule_id": "scan_packet",
                })
            if not rows:
                continue
            with conn.pipeline(), provenance.source("ocr", f"scan_packet:{packet['packet_id']}"):
                with conn.cursor() as cur:
                    invoice_id = upsert_invoice(cur, rows[0])
                for row in rows:
                    stats = process_file(conn, row, upload=upload, invoice_id=invoice_id)
                    for key in totals:
                        totals[key] += stats.get(key, 0)
            fields = FiscalFields()
            for ref, dtype in zip(refs, packet["page_types"].split("|")):
                if dtype != "factura_fiscal":
                    continue
                path, page = ref.rsplit("#", 1)
                cache = _read_cache(path) or {}
                records = cache.get("pages") or []
                if 0 < int(page) <= len(records):
                    fields.merge(extract(records[int(page) - 1].get("text") or ""))
            with conn.cursor() as cur, provenance.source("ocr", f"scan_packet:{packet['packet_id']}"):
                invoice_id = str(invoice_id)
                role_stats: Counter = Counter()
                write_invoice_fields(cur, invoice_id, fields, role_stats)
                link_fiscal_roles(cur, invoice_id, fields, role_stats)
                for key, n in role_stats.items():
                    counts[key] = counts.get(key, 0) + n
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            bump(f"error:{type(exc).__name__}")
            print(f"packet {packet['packet_id']}: {type(exc).__name__}", file=sys.stderr)
            continue
        loaded += 1
        if limit and loaded >= limit:
            break
    return {**totals, **counts, "packets_loaded": loaded}


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
    parser.add_argument(
        "--scan-packets",
        nargs="?",
        const=str(ROOT / "output" / "invoices" / "scan-packets.csv"),
        default="",
        help="Load segmented scanner packets (default output/invoices/scan-packets.csv)",
    )
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--shard", default="", help="i/n: load only packets whose key hashes to shard i of n")
    args = parser.parse_args()
    shard = None
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        if not 0 <= i < n:
            parser.error("--shard must be i/n with 0 <= i < n")
        shard = (i, n)

    if args.scan_packets:
        conn = connect()
        url = load_env().get("DATABASE_URL_UNPOOLED") or load_env()["DATABASE_URL"]
        provenance.start_run(url, "upload_documents_to_blob.scan_packets", vars(args), apply=True)
        try:
            totals = load_scan_packets(
                conn,
                Path(args.scan_packets),
                min_confidence=args.min_confidence,
                upload=not args.no_upload,
                limit=args.limit,
                shard=shard,
            )
        finally:
            conn.close()
            provenance.finish_run(url, locals().get("totals") or {})
        print("Done", totals)
        return

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
    url = load_env().get("DATABASE_URL_UNPOOLED") or load_env()["DATABASE_URL"]
    provenance.start_run(url, "upload_documents_to_blob", vars(args), apply=True)
    totals = {"pages": 0, "uploaded": 0, "failed": 0, "skipped": 0, "titular_review": 0}
    try:
        for index, row in enumerate(rows, start=1):
            stats = process_file(
                conn,
                row,
                upload=not args.no_upload,
                metadata_only=args.metadata_only,
            )
            for key in totals:
                totals[key] += stats.get(key, 0)
            if index % 10 == 0 or index == len(rows):
                print(
                    f"File {index:,}/{len(rows):,} pages={totals['pages']:,} "
                    f"uploaded={totals['uploaded']:,} failed={totals['failed']:,} "
                    f"skipped={totals['skipped']:,}"
                )
    finally:
        conn.close()
        provenance.finish_run(url, totals)
    print("Done", totals)


if __name__ == "__main__":
    main()
