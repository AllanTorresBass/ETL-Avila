#!/usr/bin/env python3
"""Link patients whose cédula was OCR'd as C.1 onto an empty beneficiario slot.

Reads output/runs/c1-patient-candidates.jsonl. A link is written only when the
loaded factura already has a titular, the beneficiario slot is empty, the
stored invoice number is a normal factura, and only one such patient claims
that factura. The titular is left in place. Dry-run is the default.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_c1_patients.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_c1_patients.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from upload_documents_to_blob import link_invoice_person  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "output" / "runs" / "c1-patient-candidates.jsonl"
SCRIPT = "repair_c1_patients"
RULE_ID = "fiscal_patient"
REASON = "patient_ci_on_fiscal_line"


def _load_candidates() -> tuple[list[str], list[str], dict[tuple[str, str], str]]:
    paths: list[str] = []
    cis: list[str] = []
    pages: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str]] = set()
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        titular = row.get("titular_ci")
        patient = row.get("patient_ci")
        path = row.get("path")
        if not titular or not patient or not path or patient == titular:
            continue
        key = (path, patient)
        pages.setdefault(key, str(row.get("page") or 1))
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
        cis.append(patient)
    return paths, cis, pages


def _finished_apply(url: str) -> str | None:
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id, counters
            FROM avila.etl_run
            WHERE script = %s AND mode = 'apply' AND finished_at IS NOT NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (SCRIPT,),
        )
        row = cur.fetchone()
    if not row:
        return None
    counters = row["counters"] or {}
    if int(counters.get("wrote_link") or 0):
        return row["id"]
    return None


def _classify(cur, paths: list[str], cis: list[str]) -> list[dict]:
    cur.execute(
        """
        WITH input AS (
          SELECT DISTINCT path, patient_ci
          FROM unnest(%s::text[], %s::text[]) AS t(path, patient_ci)
        ),
        docs AS (
          SELECT DISTINCT sf.backup_path AS path, i.invoice_number, i.id AS invoice_id
          FROM avila.source_file sf
          JOIN avila.document d ON d.source_file_id = sf.id
          JOIN avila.invoice i ON i.id = d.invoice_id
          WHERE d.document_type = 'factura_fiscal'
        )
        SELECT t.path, t.patient_ci, i.id::text AS invoice_id, i.invoice_number,
               p.id::text AS person_id,
               CASE
                 WHEN p.id IS NULL THEN 'no_person'
                 WHEN ip.role = 'beneficiario' THEN 'linked'
                 WHEN ip.role = 'titular' THEN 'linked_as_titular'
                 WHEN EXISTS (
                   SELECT 1 FROM avila.invoice_person any_ip
                   WHERE any_ip.person_id = p.id
                     AND any_ip.role IN ('titular', 'beneficiario')
                 ) THEN 'role_elsewhere'
                 ELSE 'sin_rol'
               END AS status,
               EXISTS (
                 SELECT 1 FROM avila.invoice_person ben
                 WHERE ben.invoice_id = i.id AND ben.role = 'beneficiario'
               ) AS slot_taken,
               EXISTS (
                 SELECT 1 FROM avila.invoice_person tip
                 WHERE tip.invoice_id = i.id AND tip.role = 'titular'
               ) AS has_titular,
               i.invoice_number ~ '^[0-9]{3,6}$' AS plain_factura
        FROM input t
        JOIN docs d ON d.path = t.path
        JOIN avila.invoice i ON i.id = d.invoice_id
        LEFT JOIN avila.person p
          ON p.identity_type = 'cedula'
         AND regexp_replace(p.identity_number, '\\D', '', 'g') = t.patient_ci
        LEFT JOIN avila.invoice_person ip
          ON ip.invoice_id = i.id AND ip.person_id = p.id
        """,
        (paths, cis),
    )
    return list(cur.fetchall())


def _safe(rows: list[dict]) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    pending: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        stats[row["status"]] += 1
        if row["status"] not in {"sin_rol", "role_elsewhere"}:
            continue
        if not row["has_titular"]:
            stats["hold_no_titular"] += 1
            continue
        if row["slot_taken"]:
            stats["hold_slot_taken"] += 1
            continue
        if not row["plain_factura"]:
            stats["hold_odd_invoice"] += 1
            continue
        identity = (row["invoice_id"], row["person_id"])
        if identity in seen:
            stats["repeat"] += 1
            continue
        seen.add(identity)
        pending.append(row)
    by_invoice: dict[str, set[str]] = defaultdict(set)
    for row in pending:
        by_invoice[row["invoice_id"]].add(row["person_id"])
    safe = []
    for row in pending:
        if len(by_invoice[row["invoice_id"]]) > 1:
            stats["hold_multi_patient"] += 1
            continue
        safe.append(row)
        stats[f"safe_{row['status']}"] += 1
    stats["safe"] = len(safe)
    return safe, stats


def _slot_open(cur, invoice_id: str, person_id: str) -> bool:
    cur.execute(
        """
        SELECT
          EXISTS (
            SELECT 1 FROM avila.invoice_person
            WHERE invoice_id = %s AND person_id = %s::uuid
          ) AS already,
          (
            SELECT count(*) FROM avila.invoice_person
            WHERE invoice_id = %s AND role = 'beneficiario'
          )::int AS beneficiaries,
          (
            SELECT count(*) FROM avila.invoice_person
            WHERE invoice_id = %s AND role = 'titular'
          )::int AS titulares
        """,
        (invoice_id, person_id, invoice_id, invoice_id),
    )
    row = cur.fetchone()
    return not row["already"] and row["beneficiaries"] == 0 and row["titulares"] == 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not CANDIDATES.is_file():
        print("candidates_missing=1")
        return 1
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    if args.apply:
        previous = _finished_apply(url)
        if previous:
            print(f"already_applied={previous}")
            return 0
    paths, cis, pages = _load_candidates()
    provenance.start_run(url, SCRIPT, {"apply": args.apply}, apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        safe, stats = _safe(_classify(cur, paths, cis))
        stats["candidates"] = len(paths)
        if args.apply:
            for row in safe:
                if not _slot_open(cur, row["invoice_id"], row["person_id"]):
                    stats["slot_filled_at_write"] += 1
                    continue
                page = pages.get((row["path"], row["patient_ci"]), "1")
                with provenance.source("ocr", f"{row['path']}#{page}"):
                    link_invoice_person(
                        cur,
                        row["invoice_id"],
                        row["person_id"],
                        "beneficiario",
                        source="fiscal_ocr",
                        rule_id=RULE_ID,
                        reason=REASON,
                    )
                stats["wrote_link"] += 1
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run")
    for key in sorted(stats):
        print(f"{key}={stats[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
