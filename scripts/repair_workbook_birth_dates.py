#!/usr/bin/env python3
"""Undo workbook birth dates that were written to the wrong person.

Miranda sábanas have one FECHA DE NACIMIENTO column, after the beneficiary
columns. The old mapping called it ``birth_date`` and wrote it on the titular.
This script re-reads every workbook row and compares, per person:

- ``claimed``: dates the corrected mapping assigns to that person.
- ``misattributed``: dates only the old mapping assigned to that person.

A stored DOB that is misattributed and not claimed is replaced by the single
claimed date, or cleared when there is none. Several claimed dates open a
``dob_conflict`` review instead. Dry-run by default; prints counts only.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_workbook_birth_dates.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_workbook_birth_dates.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from person_upsert import fold_person_name  # noqa: E402
from workbook_enrichment.db import connect, database_url  # noqa: E402
from workbook_enrichment.discover import BACKUP, iter_normalized_rows, iter_workbook_paths  # noqa: E402
from workbook_enrichment.upsert_persons import row_is_titular_self, titular_birth_date  # noqa: E402

Key = tuple[str, str]


def _key(ci: str | None, name: str | None) -> Key | None:
    if ci:
        return ("ci", ci)
    if name:
        return ("name", fold_person_name(name))
    return None


def attributions(row: dict) -> tuple[list[tuple[Key, object]], list[tuple[Key, object]]]:
    """(corrected, legacy) person-key → DOB pairs for one normalized row."""
    titular = _key(row.get("titular_ci"), row.get("titular_name"))
    beneficiario = _key(row.get("beneficiario_ci"), row.get("beneficiario_name"))
    same = row_is_titular_self(row)
    if same:
        beneficiario = titular or beneficiario

    corrected: list[tuple[Key, object]] = []
    t_birth = titular_birth_date(row, same_person=same)
    if titular and t_birth:
        corrected.append((titular, t_birth))
    if beneficiario and row.get("beneficiario_birth_date") and not same:
        corrected.append((beneficiario, row["beneficiario_birth_date"]))

    legacy: list[tuple[Key, object]] = []
    old_birth = row.get("birth_date") or row.get("beneficiario_birth_date")
    if titular and old_birth:
        legacy.append((titular, old_birth))
    if beneficiario and not same:
        old_ben = row.get("beneficiario_birth_date") or old_birth
        if old_ben:
            legacy.append((beneficiario, old_ben))
    return corrected, legacy


def decide(stored, claimed: set, misattributed: set) -> tuple[str, object]:
    """Return (action, new_value). Actions: keep, set, clear, conflict."""
    if stored is None:
        return "keep", None
    if stored in claimed:
        return ("conflict", None) if len(claimed) > 1 else ("keep", None)
    if stored not in misattributed:
        return "keep", None
    if len(claimed) == 1:
        return "set", next(iter(claimed))
    if not claimed:
        return "clear", None
    return "conflict", None


def collect() -> tuple[dict[Key, set], dict[Key, set], Counter]:
    claimed: dict[Key, set] = defaultdict(set)
    legacy: dict[Key, set] = defaultdict(set)
    stats: Counter = Counter()
    for path in iter_workbook_paths(BACKUP):
        relative = str(path.relative_to(BACKUP))
        stats["files"] += 1
        try:
            for _sheet, _row_number, row in iter_normalized_rows(path, relative):
                stats["rows"] += 1
                corrected, old = attributions(row)
                for key, value in corrected:
                    claimed[key].add(value)
                for key, value in old:
                    legacy[key].add(value)
        except Exception:  # noqa: BLE001
            stats["file_errors"] += 1
    misattributed = {k: v - claimed.get(k, set()) for k, v in legacy.items()}
    return claimed, {k: v for k, v in misattributed.items() if v}, stats


def _find_person(cur, key: Key):
    if key[0] == "ci":
        cur.execute(
            "SELECT id, birth_date FROM avila.person WHERE identity_type = 'cedula' AND identity_number = %s",
            (key[1],),
        )
        return cur.fetchone()
    cur.execute(
        "SELECT id, birth_date FROM avila.person WHERE name_folded = %s AND identity_number IS NULL",
        (key[1],),
    )
    rows = cur.fetchall()
    return rows[0] if len(rows) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    url = database_url()
    provenance.start_run(url, "repair_workbook_birth_dates", vars(args), apply=args.apply)
    claimed, misattributed, stats = collect()
    stats["persons_with_misattributed"] = len(misattributed)
    conn = connect()
    try:
        with conn.cursor() as cur, provenance.source("workbook", "repair_workbook_birth_dates"):
            for key, wrong in misattributed.items():
                person = _find_person(cur, key)
                if not person:
                    stats["person_not_found"] += 1
                    continue
                action, value = decide(person["birth_date"], claimed.get(key, set()), wrong)
                stats[f"action:{action}"] += 1
                if action in {"set", "clear"} and person["birth_date"]:
                    born = person["birth_date"].year
                    stats[f"{action}:old_dob_{'minor' if born >= 2008 else 'adult'}"] += 1
                if action == "keep":
                    continue
                if action == "conflict":
                    provenance.open_review(
                        cur,
                        kind="dob_conflict",
                        dedupe_key=f"dob_conflict:{person['id']}:workbook",
                        person_id=person["id"],
                        evidence={"claimed_dates": len(claimed.get(key, set()))},
                    )
                    continue
                cur.execute(
                    "UPDATE avila.person SET birth_date = %s, updated_at = now() WHERE id = %s",
                    (value, person["id"]),
                )
                provenance.record(
                    cur,
                    entity="person",
                    entity_id=person["id"],
                    field="birth_date",
                    old=person["birth_date"],
                    new=value,
                    rule_id="repair_workbook_dob",
                    reason="beneficiary DOB column had been written on the titular",
                )
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
        provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
