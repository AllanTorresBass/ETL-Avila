#!/usr/bin/env python3
"""Fill titular phone and address from workbook columns. Dry-run by default.

Sábana and claves supply the titular phone. Relación supplies the titular phone
and address. The emergency-contact column is the only phone written on a
different beneficiario. A household number that an older load copied onto that
beneficiario is cleared when it still matches. Cintillo and AMP image sheets
are skipped. Nothing is overwritten: a different stored value opens
phone_conflict or address_conflict.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_workbook_contact.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_workbook_contact.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from contact_extract import canonical_phone, same_value  # noqa: E402
from workbook_enrichment.canonical import guess_family  # noqa: E402
from workbook_enrichment.db import connect, database_url  # noqa: E402
from workbook_enrichment.discover import BACKUP, iter_normalized_rows, iter_workbook_paths  # noqa: E402
from workbook_enrichment.upsert_persons import contact_assignments  # noqa: E402

Key = tuple[str, str]
SKIP_FAMILIES = {"cintillo", "amp"}


def _collapse(field_name: str, values: set[str]) -> list[str]:
    groups: list[list[str]] = []
    for value in values:
        placed = False
        for group in groups:
            if same_value(field_name, group[0], value):
                group.append(value)
                placed = True
                break
        if not placed:
            groups.append([value])
    chosen = []
    for group in groups:
        if field_name == "address":
            chosen.append(max(group, key=len))
        else:
            chosen.append(canonical_phone(group[0]) or group[0])
    return chosen


def _decide(field_name: str, stored: str | None, values: set[str]) -> tuple[str, str | None]:
    """Return fill, keep, or conflict, plus the value to write."""
    choices = _collapse(field_name, values)
    if not choices:
        return "keep", None
    if field_name == "phone" and len(choices) > 1:
        mobiles = [value for value in choices if value[1] == "4"]
        landlines = [value for value in choices if value[1] == "2"]
        if len(mobiles) == 1 and len(mobiles) + len(landlines) == len(choices):
            choices = mobiles
        else:
            return "conflict", None
    if len(choices) > 1:
        return "conflict", None
    incoming = choices[0]
    if not stored:
        return "fill", incoming
    if same_value(field_name, stored, incoming):
        return "keep", incoming
    return "conflict", None


def collect() -> tuple[dict, dict, dict, Counter]:
    fills: dict[Key, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    clears: dict[Key, set[str]] = defaultdict(set)
    refs: dict[tuple[Key, str], str] = {}
    stats: Counter = Counter()
    for path in iter_workbook_paths(BACKUP):
        relative = str(path.relative_to(BACKUP))
        if guess_family(relative, []) in SKIP_FAMILIES:
            stats["skipped_family"] += 1
            continue
        stats["files"] += 1
        try:
            for sheet, row_number, row in iter_normalized_rows(path, relative):
                stats["rows"] += 1
                ref = f"{relative}:{sheet}:{row_number}"
                for key, field_name, value in contact_assignments(row):
                    if field_name == "phone_clear_if":
                        clears[key].add(value)
                        continue
                    fills[key][field_name].add(value)
                    refs.setdefault((key, field_name), ref)
        except Exception:  # noqa: BLE001
            stats["file_errors"] += 1
    return fills, clears, refs, stats


def _load_people(cur) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    cur.execute(
        """
        SELECT id::text AS id, identity_type::text AS identity_type,
               identity_number, name_folded, phone, address, notes
        FROM avila.person
        """
    )
    by_ci: dict[str, dict] = {}
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in cur.fetchall():
        if row["identity_type"] == "cedula" and row["identity_number"]:
            by_ci[row["identity_number"]] = row
        elif not row["identity_number"] and row["name_folded"]:
            by_name[row["name_folded"]].append(row)
    return by_ci, by_name


def _find_person(key: Key, by_ci: dict[str, dict], by_name: dict[str, list[dict]]):
    if key[0] == "ci":
        return by_ci.get(key[1])
    rows = by_name.get(key[1]) or []
    return rows[0] if len(rows) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    url = database_url()
    provenance.start_run(url, "repair_workbook_contact", {"apply": args.apply}, apply=args.apply)
    fills, clears, refs, stats = collect()
    stats["persons_with_phone"] = sum(1 for fields in fills.values() if fields.get("phone"))
    stats["persons_with_address"] = sum(1 for fields in fills.values() if fields.get("address"))
    conn = connect()
    try:
        with conn.cursor() as cur:
            by_ci, by_name = _load_people(cur)
            seen: set[str] = set()
            for key, fields in fills.items():
                person = _find_person(key, by_ci, by_name)
                if not person:
                    stats["person_not_found"] += 1
                    continue
                seen.add(person["id"])
                for field_name in ("phone", "address"):
                    values = fields.get(field_name) or set()
                    if not values:
                        continue
                    action, incoming = _decide(field_name, person.get(field_name), values)
                    stats[f"{field_name}:{action}"] += 1
                    ref = refs.get((key, field_name))
                    with provenance.source("workbook", ref):
                        if action == "conflict":
                            provenance.open_review(
                                cur,
                                kind=f"{field_name}_conflict",
                                dedupe_key=f"{field_name}_conflict:{person['id']}:workbook",
                                person_id=person["id"],
                                evidence={"sources": len(values), "source_ref": ref},
                            )
                            continue
                        if action != "fill":
                            continue
                        cur.execute(
                            f"UPDATE avila.person SET {field_name} = %s, updated_at = now() WHERE id = %s",
                            (incoming, person["id"]),
                        )
                        person[field_name] = incoming
                        provenance.record(
                            cur,
                            entity="person",
                            entity_id=person["id"],
                            field=field_name,
                            old=None,
                            new=incoming,
                            rule_id=f"workbook_{field_name}",
                            confidence=0.75,
                            reason="workbook column belongs to the titular",
                        )
            for key, phones in clears.items():
                person = _find_person(key, by_ci, by_name)
                if not person or not person.get("phone"):
                    continue
                stored = canonical_phone(person["phone"])
                if not stored or stored not in phones:
                    continue
                own = fills.get(key, {}).get("phone") or set()
                if any(same_value("phone", stored, value) for value in own):
                    continue
                stats["phone:cleared_from_beneficiario"] += 1
                with provenance.source("workbook", "household phone was on the beneficiario"):
                    cur.execute(
                        "UPDATE avila.person SET phone = NULL, updated_at = now() WHERE id = %s",
                        (person["id"],),
                    )
                    provenance.record(
                        cur,
                        entity="person",
                        entity_id=person["id"],
                        field="phone",
                        old=person["phone"],
                        new=None,
                        rule_id="workbook_phone_clear",
                        confidence=0.8,
                        reason="household phone had been written on the beneficiario",
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
