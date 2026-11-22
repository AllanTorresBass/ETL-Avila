#!/usr/bin/env python3
"""Restore held C.1 patients when the fiscal page still names them.

Reads the cédulas in output/runs/sin-rol-claro.md and the OCR candidate file.
Links the patient as beneficiario when that page's factura is empty, or
replaces a beneficiario who has no cédula. A multi-factura range is left
alone. Dry-run is the default.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_sin_rol_holds.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_sin_rol_holds.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ocr_invoice_pages  # noqa: E402
import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from fiscal_extract import extract  # noqa: E402
from sin_rol_holds import decide_hold  # noqa: E402
from upload_documents_to_blob import link_invoice_person  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "output" / "runs" / "c1-patient-candidates.jsonl"
LIST = ROOT / "output" / "runs" / "sin-rol-claro.md"
PLAN = ROOT / "output" / "runs" / "sin-rol-hold-plan.json"
SCRIPT = "repair_sin_rol_holds"
RULE_ID = "fiscal_patient"
LINK_REASON = "patient_ci_on_fiscal_line"
CLEAR_REASON = "nameless_slot_is_not_the_patient"


def _cis(path: Path) -> list[str]:
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cell = line.split("|")[1].strip()
        digits = re.sub(r"\D", "", cell)
        if 6 <= len(digits) <= 9:
            found.append(digits)
    return list(dict.fromkeys(found))


def _page_text(path: str, page: int) -> str:
    cached = ocr_invoice_pages._read_cache(path)
    if not cached:
        return ""
    for item in cached.get("pages") or []:
        if int(item.get("page") or 0) == int(page):
            return item.get("text") or ""
    pages = cached.get("pages") or []
    return (pages[0].get("text") or "") if pages else ""


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


def _candidates(cis: list[str]) -> list[dict]:
    rows = []
    seen = set()
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        patient = re.sub(r"\D", "", str(row.get("patient_ci") or ""))
        titular = re.sub(r"\D", "", str(row.get("titular_ci") or ""))
        path = row.get("path")
        if patient not in cis or not path or not titular or patient == titular:
            continue
        key = (path, patient, int(row.get("page") or 1))
        if key in seen:
            continue
        seen.add(key)
        row["patient_ci"] = patient
        row["titular_ci"] = titular
        rows.append(row)
    return rows


def _plan(cur, hits: list[dict]) -> list[dict]:
    paths = list({h["path"] for h in hits})
    cis = list({h["patient_ci"] for h in hits})
    cur.execute(
        """
        SELECT id::text AS person_id,
               regexp_replace(identity_number, '\\D', '', 'g') AS ci,
               full_name
        FROM avila.person
        WHERE identity_type = 'cedula'
          AND regexp_replace(identity_number, '\\D', '', 'g') = ANY(%s)
        """,
        (cis,),
    )
    people = {}
    for row in cur.fetchall():
        people.setdefault(row["ci"], row)
    cur.execute(
        """
        SELECT sf.backup_path AS path, i.id::text AS invoice_id, i.invoice_number
        FROM avila.source_file sf
        JOIN avila.document d ON d.source_file_id = sf.id
        JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE d.document_type = 'factura_fiscal'
          AND sf.backup_path = ANY(%s)
        """,
        (paths,),
    )
    invoices_by_path: dict[str, list] = {}
    for row in cur.fetchall():
        invoices_by_path.setdefault(row["path"], []).append(dict(row))
    invoice_ids = list({r["invoice_id"] for rows in invoices_by_path.values() for r in rows})
    occupants: dict[str, list] = {}
    cleared: set[tuple[str, str]] = set()
    if invoice_ids:
        cur.execute(
            """
            SELECT ip.invoice_id::text AS invoice_id, ip.role, ip.source,
                   regexp_replace(p.identity_number, '\\D', '', 'g') AS ci,
                   p.full_name, p.id::text AS person_id
            FROM avila.invoice_person ip
            JOIN avila.person p ON p.id = ip.person_id
            WHERE ip.invoice_id = ANY(%s::uuid[])
              AND ip.role IN ('titular', 'beneficiario')
            """,
            (invoice_ids,),
        )
        for row in cur.fetchall():
            occupants.setdefault(row["invoice_id"], []).append(dict(row))
        cur.execute(
            """
            SELECT split_part(entity_id, ':', 1) AS invoice_id,
                   split_part(entity_id, ':', 2) AS person_id
            FROM avila.field_provenance
            WHERE entity = 'invoice_person'
              AND field = 'role'
              AND new_value_hash IS NULL
              AND split_part(entity_id, ':', 1) = ANY(%s)
            """,
            (invoice_ids,),
        )
        cleared = {(r["invoice_id"], r["person_id"]) for r in cur.fetchall()}

    planned = []
    seen = set()
    for hit in hits:
        person = people.get(hit["patient_ci"])
        if not person:
            continue
        text = _page_text(hit["path"], int(hit.get("page") or 1))
        fields = extract(text)
        for inv in invoices_by_path.get(hit["path"], []):
            identity = (inv["invoice_id"], person["person_id"])
            if identity in seen:
                continue
            rows = occupants.get(inv["invoice_id"], [])
            titulares = [r for r in rows if r["role"] == "titular"]
            beneficiaries = [r for r in rows if r["role"] == "beneficiario"]
            decision = decide_hold(
                page_patient_ci=fields.patient_ci,
                page_titular_ci=fields.titular_ci,
                patient_ci=hit["patient_ci"],
                patient_name=person["full_name"],
                stored_invoice=inv["invoice_number"],
                ocr_invoice=fields.invoice_number,
                titular_ci=titulares[0]["ci"] if len(titulares) == 1 else None,
                titular_count=len(titulares),
                beneficiaries=[
                    {"ci": b["ci"], "name": b["full_name"], "source": b["source"]}
                    for b in beneficiaries
                ],
                patient_was_cleared=(inv["invoice_id"], person["person_id"]) in cleared,
                already_on_invoice=any(r["person_id"] == person["person_id"] for r in rows),
            )
            if decision.action == "skip":
                continue
            seen.add(identity)
            drop = beneficiaries[0] if decision.action == "replace" else None
            planned.append(
                {
                    "action": decision.action,
                    "reason": decision.reason,
                    "invoice_id": inv["invoice_id"],
                    "invoice_number": inv["invoice_number"],
                    "person_id": person["person_id"],
                    "patient_ci": hit["patient_ci"],
                    "path": hit["path"],
                    "page": int(hit.get("page") or 1),
                    "drop_person_id": drop["person_id"] if drop else None,
                }
            )
    return planned


def _still_safe(cur, row: dict) -> bool:
    cur.execute(
        """
        SELECT ip.role, ip.source, p.id::text AS person_id,
               regexp_replace(p.identity_number, '\\D', '', 'g') AS ci
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = %s::uuid
          AND ip.role IN ('titular', 'beneficiario')
        """,
        (row["invoice_id"],),
    )
    rows = list(cur.fetchall())
    if any(r["person_id"] == row["person_id"] for r in rows):
        return False
    titulares = [r for r in rows if r["role"] == "titular"]
    beneficiaries = [r for r in rows if r["role"] == "beneficiario"]
    if len(titulares) != 1:
        return False
    if row["action"] == "link":
        return not beneficiaries
    if row["action"] != "replace" or len(beneficiaries) != 1:
        return False
    ben = beneficiaries[0]
    return ben["person_id"] == row["drop_person_id"] and not ben["ci"] and ben["source"] != "workbook"


def _drop_nameless(cur, row: dict) -> None:
    cur.execute(
        """
        SELECT role::text AS role
        FROM avila.invoice_person
        WHERE invoice_id = %s::uuid AND person_id = %s::uuid
        """,
        (row["invoice_id"], row["drop_person_id"]),
    )
    current = cur.fetchone()
    if not current:
        return
    provenance.record(
        cur,
        entity="invoice_person",
        entity_id=f"{row['invoice_id']}:{row['drop_person_id']}",
        field="role",
        old=current["role"],
        new=None,
        rule_id=RULE_ID,
        reason=CLEAR_REASON,
    )
    cur.execute(
        """
        DELETE FROM avila.invoice_person
        WHERE invoice_id = %s::uuid AND person_id = %s::uuid AND role = 'beneficiario'
        """,
        (row["invoice_id"], row["drop_person_id"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--list", type=Path, default=LIST)
    args = parser.parse_args()
    if not args.list.is_file() or not CANDIDATES.is_file():
        print("inputs_missing=1")
        return 1
    cis = _cis(args.list)
    hits = _candidates(cis)
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    if args.apply:
        previous = _finished_apply(url)
        if previous:
            print(f"already_applied={previous}")
            return 0
    provenance.start_run(url, SCRIPT, {"apply": args.apply, "people": len(cis)}, apply=args.apply)
    stats: Counter = Counter()
    stats["people"] = len(cis)
    stats["pages"] = len(hits)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        planned = _plan(cur, hits)
        for row in planned:
            stats[row["action"]] += 1
            stats[row["reason"]] += 1
        if args.apply:
            for row in planned:
                if not _still_safe(cur, row):
                    stats["changed_before_write"] += 1
                    continue
                with provenance.source("ocr", f"{row['path']}#{row['page']}"):
                    if row["action"] == "replace":
                        _drop_nameless(cur, row)
                        stats["cleared_nameless"] += 1
                    link_invoice_person(
                        cur,
                        row["invoice_id"],
                        row["person_id"],
                        "beneficiario",
                        source="fiscal_ocr",
                        rule_id=RULE_ID,
                        reason=LINK_REASON,
                    )
                stats["wrote_link"] += 1
            conn.commit()
        else:
            PLAN.write_text(json.dumps(planned, ensure_ascii=False, indent=2), encoding="utf-8")
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run")
    for key in sorted(stats):
        print(f"{key}={stats[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
