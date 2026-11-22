#!/usr/bin/env python3
"""Link orphan cédulas only into an empty factura role.

Walks workbook rows whose cédula belongs to a person with no factura role.
Invoice truth removals stay unlinked. A factura that already has that role
becomes a ``ci_conflict`` review. Dry-run is the default.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_orphan_cedulas.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_orphan_cedulas.py --apply

Stdout is counts. A finished ``--apply`` of this script blocks a second one.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from upload_documents_to_blob import link_invoice_person  # noqa: E402
from workbook_enrichment.discover import (  # noqa: E402
    BACKUP,
    iter_normalized_rows,
    iter_workbook_paths,
)
from workbook_enrichment.orphan_cedulas import (  # noqa: E402
    OCCUPIED,
    ci_key,
    decide_orphan_row,
)

RULE_ID = "orphan_ci_workbook"
SCRIPT = "repair_orphan_cedulas"
AMBIGUOUS = ""


def _invoice_keys(number: str) -> list[str]:
    keys = [number]
    if number.isdigit():
        stripped = str(int(number))
        padded = number.zfill(6)
        for key in (stripped, padded):
            if key not in keys:
                keys.append(key)
    return keys


def _finished_apply(url: str) -> str | None:
    """A prior apply blocks another only when it wrote a link or a review."""
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
    if int(counters.get("wrote_link") or 0) or int(counters.get("wrote_review") or 0):
        return row["id"]
    return None


def _load_cohort(url: str) -> tuple[dict[str, str], set[str], set[str], set[str], Counter]:
    stats: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id::text AS id,
                   regexp_replace(coalesce(p.identity_number, ''), '\\D', '', 'g') AS digits,
                   EXISTS (
                     SELECT 1 FROM avila.field_provenance fp
                     WHERE fp.entity = 'invoice_person'
                       AND fp.field = 'role'
                       AND fp.new_value_hash IS NULL
                       AND fp.rule_id IN ('invoice_truth_titular', 'invoice_truth_beneficiario')
                       AND split_part(fp.entity_id, ':', 2) = p.id::text
                   ) AS truth_removed,
                   EXISTS (
                     SELECT 1 FROM avila.review_item ri
                     WHERE ri.person_id = p.id
                       AND ri.kind = 'ci_conflict'
                       AND ri.status = 'open'
                   ) AS open_conflict
            FROM avila.person p
            WHERE p.identity_type = 'cedula'::avila.identity_type
              AND coalesce(p.identity_number, '') <> ''
              AND NOT EXISTS (
                SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id
              )
            """
        )
        rows = cur.fetchall()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = ci_key(row["digits"])
        if not key:
            stats["no_digits"] += 1
            continue
        grouped[key].append(row)
    people: dict[str, str] = {}
    eligible: set[str] = set()
    removed: set[str] = set()
    conflicts: set[str] = set()
    for key, group in grouped.items():
        ids = {row["id"] for row in group}
        if len(ids) > 1:
            stats["digit_collision"] += len(ids)
            continue
        row = group[0]
        people[key] = row["id"]
        if row["truth_removed"]:
            removed.add(key)
        elif row["open_conflict"]:
            conflicts.add(key)
        else:
            eligible.add(key)
    stats["people_orphan"] = len(people)
    stats["people_eligible"] = len(eligible)
    stats["people_truth_removed"] = len(removed)
    stats["people_open_conflict"] = len(conflicts)
    return people, eligible, removed, conflicts, stats


def _load_invoices(url: str) -> tuple[dict[str, str], dict[str, dict]]:
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT id::text AS id, invoice_number FROM avila.invoice")
        numbers = cur.fetchall()
        cur.execute(
            """
            SELECT ip.invoice_id::text AS invoice_id, ip.role::text AS role,
                   regexp_replace(coalesce(p.identity_number, ''), '\\D', '', 'g') AS digits
            FROM avila.invoice_person ip
            JOIN avila.person p ON p.id = ip.person_id
            WHERE ip.role IN ('titular', 'beneficiario')
            """
        )
        links = cur.fetchall()
    index: dict[str, str] = {}
    for row in numbers:
        invoice_id = row["id"]
        for key in _invoice_keys(row["invoice_number"] or ""):
            previous = index.get(key)
            if previous is None:
                index[key] = invoice_id
            elif previous != invoice_id:
                index[key] = AMBIGUOUS
    slots: dict[str, dict] = {}
    for row in links:
        slot = slots.setdefault(row["invoice_id"], {"titular": None, "beneficiarios": set()})
        key = ci_key(row["digits"])
        if row["role"] == "titular":
            if slot["titular"] is None and key:
                slot["titular"] = key
            else:
                slot["titular"] = OCCUPIED
        elif key:
            slot["beneficiarios"].add(key)
    return index, slots


def _note(stats: Counter, people: dict[str, set[str]], bucket: str, person_id: str) -> None:
    stats[bucket] += 1
    people[bucket].add(person_id)


def _walk(url_stats: Counter, people_by_ci, eligible, removed, conflicts, index, slots):
    stats = url_stats
    watched = eligible | removed | conflicts
    touched: dict[str, set[str]] = defaultdict(set)
    plans: list[dict] = []
    seen_links: set[tuple[str, str, str]] = set()
    seen_reviews: set[tuple[str, str, str]] = set()
    paths = list(iter_workbook_paths(BACKUP))
    stats["workbook_files"] = len(paths)
    for index_no, path in enumerate(paths, start=1):
        relative = str(path.relative_to(BACKUP))
        for sheet, row_number, row in iter_normalized_rows(path, relative):
                stats["workbook_rows"] += 1
                keys = [ci_key(row.get("titular_ci")), ci_key(row.get("beneficiario_ci"))]
                if not any(key in watched for key in keys if key):
                    continue
                stats["matched_rows"] += 1
                number = row.get("invoice_number")
                invoice_id = index.get(number) if number else None
                if invoice_id == AMBIGUOUS:
                    stats["invoice_number_ambiguous"] += 1
                    continue
                found = bool(invoice_id)
                slot = (
                    slots.setdefault(invoice_id, {"titular": None, "beneficiarios": set()})
                    if invoice_id
                    else None
                )
                decisions = decide_orphan_row(
                    row,
                    invoice_found=found,
                    titular_ci=None if slot is None else slot["titular"],
                    beneficiario_cis=set() if slot is None else set(slot["beneficiarios"]),
                    eligible_cis=eligible,
                    truth_removed_cis=removed,
                    open_conflict_cis=conflicts,
                )
                source_ref = f"{relative}:{sheet}:{row_number}"
                for decision in decisions:
                    person_id = people_by_ci.get(decision.ci)
                    if not person_id:
                        stats["missing_person"] += 1
                        continue
                    if decision.action in {"link_titular", "link_beneficiario"}:
                        identity = (invoice_id, person_id, decision.role)
                        if identity in seen_links:
                            stats["repeat_link"] += 1
                            continue
                        seen_links.add(identity)
                        _note(stats, touched, f"safe_{decision.role}", person_id)
                        plans.append(
                            {
                                "action": decision.action,
                                "role": decision.role,
                                "reason": decision.reason,
                                "person_id": person_id,
                                "invoice_id": invoice_id,
                                "source_ref": source_ref,
                                "incoming_hash": provenance.value_hash(decision.ci),
                                "stored_hash": provenance.value_hash(
                                    None if slot is None or slot["titular"] in {None, OCCUPIED}
                                    else slot["titular"]
                                ),
                            }
                        )
                        if decision.role == "titular":
                            slot["titular"] = decision.ci
                        else:
                            slot["beneficiarios"].add(decision.ci)
                        continue
                    if decision.action == "review":
                        identity = (invoice_id, person_id, decision.role)
                        if identity in seen_reviews:
                            stats["repeat_review"] += 1
                            continue
                        seen_reviews.add(identity)
                        stored = slot["titular"] if decision.role == "titular" else None
                        _note(stats, touched, "packet_conflict", person_id)
                        plans.append(
                            {
                                "action": "review",
                                "role": decision.role,
                                "reason": decision.reason,
                                "person_id": person_id,
                                "invoice_id": invoice_id,
                                "source_ref": source_ref,
                                "incoming_hash": provenance.value_hash(decision.ci),
                                "stored_hash": provenance.value_hash(
                                    None if stored in {None, OCCUPIED} else stored
                                ),
                            }
                        )
                        continue
                    _note(stats, touched, decision.reason, person_id)
        if index_no == 1 or index_no % 25 == 0 or index_no == len(paths):
            print(
                f"files={index_no}/{len(paths)} matched_rows={stats['matched_rows']}",
                flush=True,
            )
    for bucket, ids in touched.items():
        stats[f"people_{bucket}"] = len(ids)
    return plans


def _slot_open(cur, invoice_id: str, person_id: str, role: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM avila.invoice_person
        WHERE invoice_id = %s AND person_id = %s::uuid
        """,
        (invoice_id, person_id),
    )
    if cur.fetchone():
        return False
    cur.execute(
        """
        SELECT count(*)::int AS n
        FROM avila.invoice_person
        WHERE invoice_id = %s AND role = %s::avila.invoice_person_role
        """,
        (invoice_id, role),
    )
    if cur.fetchone()["n"]:
        return False
    if role == "beneficiario":
        cur.execute(
            """
            SELECT count(*)::int AS n
            FROM avila.invoice_person
            WHERE invoice_id = %s AND role = 'titular'
            """,
            (invoice_id,),
        )
        if cur.fetchone()["n"] != 1:
            return False
    return True


def _apply(url: str, plans: list[dict], stats: Counter) -> None:
    ordered = sorted(
        plans,
        key=lambda plan: (plan["action"] == "review", plan["role"] != "titular"),
    )
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        for plan in ordered:
            with provenance.source("workbook", plan["source_ref"]):
                if plan["action"] == "review":
                    provenance.open_review(
                        cur,
                        kind="ci_conflict",
                        dedupe_key=f"ci_conflict:orphan:{plan['invoice_id']}:{plan['person_id']}",
                        person_id=plan["person_id"],
                        invoice_id=plan["invoice_id"],
                        evidence={
                            "slot": plan["role"],
                            "stored_hash": plan["stored_hash"],
                            "incoming_hash": plan["incoming_hash"],
                        },
                    )
                    stats["wrote_review"] += 1
                    continue
                if not _slot_open(cur, plan["invoice_id"], plan["person_id"], plan["role"]):
                    stats["slot_filled_at_write"] += 1
                    continue
                link_invoice_person(
                    cur,
                    plan["invoice_id"],
                    plan["person_id"],
                    plan["role"],
                    source="workbook",
                    rule_id=RULE_ID,
                    reason=plan["reason"],
                )
                stats["wrote_link"] += 1
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    if args.apply:
        previous = _finished_apply(url)
        if previous:
            print(f"already_applied={previous}")
            return 0
    provenance.start_run(url, SCRIPT, {"apply": args.apply}, apply=args.apply)
    people, eligible, removed, conflicts, stats = _load_cohort(url)
    index, slots = _load_invoices(url)
    plans = _walk(stats, people, eligible, removed, conflicts, index, slots)
    if args.apply:
        _apply(url, plans, stats)
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run")
    for key in sorted(stats):
        print(f"{key}={stats[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
