#!/usr/bin/env python3
"""Apply self and pair decisions from the invoice-truth file.

Dry-run unless ``--apply`` is set. Review rows are not linked. ``unassigned_cards``
opens the existing ``multiple_ci`` review on apply. A stored usable name that is a
different person is a ``ci_conflict`` and that factura is skipped.

  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py
  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py --invoices 12843,7394
  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py --apply --invoices 12843

Does not re-read OCR. Phone, address, and birth date are left untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from person_name_gate import is_usable_person_name  # noqa: E402
from person_upsert import upsert_by_ci, upsert_by_name  # noqa: E402
from upload_documents_to_blob import (  # noqa: E402
    _names_refer_to_same_person,
    link_invoice_person,
    titular_promotion_blocker,
    try_promote_ci_titular,
)

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "output" / "runs" / "invoice-truth-decisions.jsonl"
PROBE_ID = "00000000-0000-0000-0000-000000000000"


def _wanted(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def load_decisions(path: Path, wanted: set[str] | None) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if wanted is not None and row.get("invoice_number") not in wanted:
            continue
        rows.append(row)
    return rows


def _person_by_ci(cur, number: str) -> dict | None:
    cur.execute(
        """
        SELECT id::text AS id, full_name
        FROM avila.person
        WHERE identity_type = 'cedula'::avila.identity_type AND identity_number = %s
        """,
        (number,),
    )
    return cur.fetchone()


def _name_conflict(stored: str | None, incoming: str | None) -> bool:
    """A usable stored name that is a different person blocks the write."""
    if not stored or not incoming:
        return False
    if not is_usable_person_name(stored):
        return False
    return not _names_refer_to_same_person(stored, incoming)


def _source_ref(decision: dict, prefix: str) -> str | None:
    path = decision.get(f"{prefix}_backup_path")
    page = decision.get(f"{prefix}_page_index")
    if path and page is not None:
        return f"{path}#{page}"
    if path:
        return path
    return None


def _open_name_conflict(cur, invoice_id: str, person_id: str) -> None:
    provenance.open_review(
        cur,
        kind="ci_conflict",
        dedupe_key=f"ci_conflict:{invoice_id}:{person_id}",
        person_id=person_id,
        invoice_id=invoice_id,
        evidence={"rule": "invoice_truth", "reason": "name_mismatch"},
    )


def _open_unassigned(cur, invoice_id: str) -> None:
    provenance.open_review(
        cur,
        kind="multiple_ci",
        dedupe_key=f"multiple_ci:{invoice_id}:invoice_truth",
        invoice_id=invoice_id,
        evidence={"rule": "invoice_truth", "reason": "unassigned_cards"},
    )


def _set_page_person(cur, decision: dict, prefix: str, person_id: str) -> None:
    document_id = decision.get(f"{prefix}_document_id")
    if not document_id or not person_id:
        return
    cur.execute(
        "SELECT person_id::text AS person_id FROM avila.document WHERE id = %s::uuid",
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        return
    old = row["person_id"]
    if old == person_id:
        return
    cur.execute(
        """
        UPDATE avila.document
        SET person_id = %s::uuid, updated_at = now()
        WHERE id = %s::uuid
        """,
        (person_id, document_id),
    )
    provenance.record(
        cur,
        entity="document",
        entity_id=document_id,
        field="person_id",
        old=old,
        new=person_id,
        rule_id="invoice_truth_page_person",
        reason=prefix,
    )


def _clear_others(cur, invoice_id: str, keep: list[str], rule_id: str, reason: str) -> None:
    cur.execute(
        """
        SELECT person_id::text AS person_id, role::text AS role
        FROM avila.invoice_person
        WHERE invoice_id = %s::uuid
          AND NOT (person_id::text = ANY(%s))
        """,
        (invoice_id, keep),
    )
    extras = cur.fetchall()
    for row in extras:
        provenance.record(
            cur,
            entity="invoice_person",
            entity_id=f"{invoice_id}:{row['person_id']}",
            field="role",
            old=row["role"],
            new=None,
            rule_id=rule_id,
            reason=reason,
        )
    if extras:
        cur.execute(
            """
            DELETE FROM avila.invoice_person
            WHERE invoice_id = %s::uuid
              AND NOT (person_id::text = ANY(%s))
            """,
            (invoice_id, keep),
        )


def _resolve_patient(cur, decision: dict, *, apply: bool) -> tuple[str | None, str]:
    number = decision.get("beneficiario_ci")
    name = decision.get("beneficiario_name")
    if number:
        if _name_conflict((_person_by_ci(cur, number) or {}).get("full_name"), name):
            return None, "name_conflict"
        person_id, action = upsert_by_ci(
            cur, identity_number=number, full_name=name, identity_type="cedula", dry_run=not apply
        )
        return person_id, action
    if name:
        person_id, action = upsert_by_name(cur, full_name=name, dry_run=not apply)
        return person_id, action
    return None, "no_patient"


def apply_decision(cur, decision: dict, *, apply: bool) -> str:
    """Return a counter key. Writes only when ``apply`` is true."""
    outcome = decision.get("outcome")
    invoice_id = decision.get("invoice_id")
    if outcome == "review":
        reason = decision.get("reason") or "review"
        if reason == "unassigned_cards" and invoice_id and apply:
            _open_unassigned(cur, invoice_id)
        return f"review_{reason}"

    if outcome not in {"self", "pair"} or not invoice_id or not decision.get("titular_ci"):
        return "skip_undecided"

    stored = _person_by_ci(cur, decision["titular_ci"])
    if _name_conflict((stored or {}).get("full_name"), decision.get("titular_name")):
        if apply and stored:
            _open_name_conflict(cur, invoice_id, stored["id"])
        return "skip_name_conflict"

    if not apply:
        probe = stored["id"] if stored else PROBE_ID
        blocker = titular_promotion_blocker(cur, invoice_id, probe)
        if blocker:
            return f"skip_{blocker}"
        return f"would_{outcome}"

    with provenance.source("ocr", _source_ref(decision, "titular")):
        titular_id, _action = upsert_by_ci(
            cur,
            identity_number=decision["titular_ci"],
            full_name=decision.get("titular_name"),
            identity_type="cedula",
            dry_run=False,
        )
        if not titular_id:
            return "skip_titular_upsert"

        patient_id = None
        if outcome == "pair":
            patient_id, patient_action = _resolve_patient(cur, decision, apply=True)
            if patient_action == "name_conflict":
                existing = _person_by_ci(cur, decision["beneficiario_ci"]) if decision.get("beneficiario_ci") else None
                if existing:
                    _open_name_conflict(cur, invoice_id, existing["id"])
                return "skip_name_conflict"
            if not patient_id:
                return "skip_beneficiario"
            if patient_id == titular_id:
                patient_id = None
                outcome = "self"

        cur.execute(
            """
            SELECT role::text AS role
            FROM avila.invoice_person
            WHERE invoice_id = %s::uuid AND person_id = %s::uuid
            """,
            (invoice_id, titular_id),
        )
        before = cur.fetchone()
        old_role = before["role"] if before else None
        promoted = try_promote_ci_titular(
            cur,
            invoice_id,
            titular_id,
            source=decision.get("titular_source") or "ocr_cedula",
        )
        if promoted != "promoted":
            return f"skip_{promoted}"
        provenance.record(
            cur,
            entity="invoice_person",
            entity_id=f"{invoice_id}:{titular_id}",
            field="role",
            old=old_role,
            new="titular",
            rule_id="invoice_truth_titular",
            reason=decision.get("titular_source"),
        )
        _set_page_person(cur, decision, "titular", titular_id)

        keep = [titular_id]
        if outcome == "pair" and patient_id:
            link_invoice_person(
                cur,
                invoice_id,
                patient_id,
                "beneficiario",
                source=decision.get("beneficiario_source") or "fiscal_ocr",
                rule_id="invoice_truth_beneficiario",
            )
            cur.execute(
                """
                UPDATE avila.invoice_person
                SET source = %s
                WHERE invoice_id = %s::uuid AND person_id = %s::uuid
                """,
                (decision.get("beneficiario_source") or "fiscal_ocr", invoice_id, patient_id),
            )
            _set_page_person(cur, decision, "beneficiario", patient_id)
            keep.append(patient_id)
            _clear_others(cur, invoice_id, keep, "invoice_truth_beneficiario", "not_in_decision")
            return "pair"

        _clear_others(cur, invoice_id, keep, "invoice_truth_titular", "self_only")
        return "self"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--invoices", help="Comma-separated factura numbers")
    parser.add_argument("--input", type=Path, default=DECISIONS)
    args = parser.parse_args()
    if not args.input.is_file():
        sys.exit(f"missing {args.input.name}")
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")

    decisions = load_decisions(args.input, _wanted(args.invoices))
    provenance.start_run(url, "invoice_truth_apply", {"apply": args.apply, "invoices": args.invoices}, apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        for decision in decisions:
            key = apply_decision(cur, decision, apply=args.apply)
            provenance.counters[key] += 1
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, {"decisions": len(decisions)})
    printable = {key: value for key, value in sorted(provenance.counters.items()) if isinstance(value, int)}
    print("apply" if args.apply else "dry-run", printable, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
