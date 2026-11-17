"""Shared avila.person upsert + provisional absorb (path loader and workbooks).

Every field write records provenance (scripts/provenance.py). Callers set the
source with ``provenance.source(kind, ref)``; ``rule_id`` names the helper.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import provenance

PERSON_FIELDS = ("full_name", "birth_date", "phone", "address")


def fold_person_name(name: str) -> str:
    """Accent-fold + lowercase + collapse whitespace for provisional keys."""
    text = unicodedata.normalize("NFD", name or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.casefold().strip()
    return re.sub(r"\s+", " ", text)


def provisional_key_for_name(name: str) -> str:
    """Name-scoped key (invoice stays on invoice_person only)."""
    return f"name:{fold_person_name(name)}"


def _merge_text(cur_val: str | None, new_val: str | None) -> str | None:
    if new_val and not cur_val:
        return new_val
    if new_val and cur_val and len(new_val) > len(cur_val):
        return new_val
    return cur_val


def _record_person_changes(cur, person_id, before: dict, after: dict, rule_id: str) -> None:
    for field in PERSON_FIELDS:
        provenance.record(
            cur,
            entity="person",
            entity_id=person_id,
            field=field,
            old=before.get(field),
            new=after.get(field),
            rule_id=rule_id,
        )


def merge_person(cur, survivor_id: str, alias_id: str, *, reason: str = "") -> dict:
    """Rewire every link from alias into survivor, then delete alias.

    Survivor keeps its own values; empty survivor fields take the alias value.
    """
    survivor_id, alias_id = str(survivor_id), str(alias_id)
    if survivor_id == alias_id:
        return {}
    cur.execute(
        f"""
        SELECT id, identity_type::text AS identity_type, identity_number, {', '.join(PERSON_FIELDS)}
        FROM avila.person WHERE id = ANY(%s::uuid[])
        """,
        ([survivor_id, alias_id],),
    )
    rows = {str(r["id"]): r for r in cur.fetchall()}
    if survivor_id not in rows or alias_id not in rows:
        return {}
    survivor, alias = rows[survivor_id], rows[alias_id]
    if survivor.get("identity_number") and alias.get("identity_number") and (
        survivor["identity_number"] != alias["identity_number"]
    ):
        raise ValueError("merge_person: survivor and alias carry different identity numbers")
    fill = {f: alias[f] for f in PERSON_FIELDS if not survivor.get(f) and alias.get(f)}
    if alias.get("identity_number") and not survivor.get("identity_number"):
        fill["identity_type"] = alias["identity_type"]
        fill["identity_number"] = alias["identity_number"]
    out: dict[str, int] = {}
    cur.execute(
        """
        UPDATE avila.invoice_person s
        SET role = a.role, parentesco = coalesce(s.parentesco, a.parentesco), source = a.source
        FROM avila.invoice_person a
        WHERE a.person_id = %s AND s.person_id = %s AND s.invoice_id = a.invoice_id
          AND s.role = 'unknown' AND a.role <> 'unknown'
        """,
        (alias_id, survivor_id),
    )
    cur.execute(
        """
        UPDATE avila.invoice_person SET person_id = %s
        WHERE person_id = %s AND NOT EXISTS (
          SELECT 1 FROM avila.invoice_person x
          WHERE x.invoice_id = avila.invoice_person.invoice_id AND x.person_id = %s)
        """,
        (survivor_id, alias_id, survivor_id),
    )
    out["invoice_person"] = cur.rowcount
    cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s", (alias_id,))
    for table in ("document", "authorization_line"):
        cur.execute(
            f"UPDATE avila.{table} SET person_id = %s WHERE person_id = %s",
            (survivor_id, alias_id),
        )
        out[table] = cur.rowcount
    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = 'merge', resolved_at = now()
        WHERE status = 'open' AND kind = 'duplicate_candidate'
          AND ((person_id = %s AND other_person_id = %s) OR (person_id = %s AND other_person_id = %s))
        """,
        (survivor_id, alias_id, alias_id, survivor_id),
    )
    # review_item cascades on person delete; keep the queue and its history on the survivor.
    for column in ("person_id", "other_person_id"):
        cur.execute(
            f"UPDATE avila.review_item SET {column} = %s WHERE {column} = %s",
            (survivor_id, alias_id),
        )
    cur.execute("DELETE FROM avila.person WHERE id = %s", (alias_id,))
    if fill:
        sets = ", ".join(
            f"{f} = %s::avila.identity_type" if f == "identity_type" else f"{f} = %s" for f in fill
        )
        cur.execute(
            f"UPDATE avila.person SET {sets}, updated_at = now() WHERE id = %s",
            (*fill.values(), survivor_id),
        )
    provenance.record(
        cur,
        entity="person",
        entity_id=survivor_id,
        field="merged_from",
        old=None,
        new=alias_id,
        rule_id="merge_person",
        reason=reason or None,
    )
    _record_person_changes(cur, survivor_id, survivor, {**survivor, **fill}, "merge_person")
    if "identity_number" in fill:
        provenance.record(
            cur,
            entity="person",
            entity_id=survivor_id,
            field="identity_number",
            old=None,
            new=fill["identity_number"],
            rule_id="merge_person",
        )
    return out


def absorb_provisional(cur, survivor_id: str, full_name: str) -> int:
    """Rewire links from same-name provisional rows into survivor; return absorbed count."""
    if not full_name:
        return 0
    folded = fold_person_name(full_name)
    cur.execute(
        """
        SELECT id, full_name FROM avila.person
        WHERE id <> %s::uuid
          AND identity_number IS NULL
          AND provisional_key IS NOT NULL
          AND (name_folded = %s OR lower(full_name) = lower(%s))
        """,
        (survivor_id, folded, full_name),
    )
    orphans = [r for r in cur.fetchall() if fold_person_name(r["full_name"] or "") == folded]
    for orphan in orphans:
        merge_person(cur, survivor_id, str(orphan["id"]), reason="same_name_provisional")
    return len(orphans)


def upsert_by_ci(
    cur,
    *,
    identity_number: str,
    full_name: str | None = None,
    identity_type: str = "cedula",
    birth_date=None,
    phone: str | None = None,
    address: str | None = None,
    dry_run: bool = False,
) -> tuple[str | None, str]:
    cur.execute(
        """
        SELECT id, full_name, birth_date, phone, address
        FROM avila.person
        WHERE identity_type = %s::avila.identity_type AND identity_number = %s
        """,
        (identity_type, identity_number),
    )
    row = cur.fetchone()
    if row:
        if dry_run:
            return str(row["id"]), "exists"
        after = {
            "full_name": _merge_text(row["full_name"], full_name),
            "birth_date": row["birth_date"] or birth_date,
            "phone": _merge_text(row["phone"], phone),
            "address": _merge_text(row["address"], address),
        }
        cur.execute(
            """
            UPDATE avila.person SET
              full_name = coalesce(%s, full_name),
              birth_date = %s,
              phone = %s,
              address = %s,
              updated_at = now()
            WHERE id = %s
            """,
            (after["full_name"], after["birth_date"], after["phone"], after["address"], row["id"]),
        )
        _record_person_changes(cur, row["id"], row, after, "upsert_by_ci")
        _flag_dob_conflict(cur, row["id"], row["birth_date"], birth_date)
        if full_name or row["full_name"]:
            absorb_provisional(cur, str(row["id"]), full_name or row["full_name"])
        return str(row["id"]), "updated"

    if dry_run:
        return None, "dry_create"
    cur.execute(
        """
        INSERT INTO avila.person (
          identity_type, identity_number, full_name, birth_date, phone, address
        ) VALUES (%s::avila.identity_type, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (identity_type, identity_number, full_name, birth_date, phone, address),
    )
    person_id = str(cur.fetchone()["id"])
    provenance.record(
        cur,
        entity="person",
        entity_id=person_id,
        field="identity_number",
        old=None,
        new=identity_number,
        rule_id="upsert_by_ci",
    )
    _record_person_changes(
        cur,
        person_id,
        {},
        {"full_name": full_name, "birth_date": birth_date, "phone": phone, "address": address},
        "upsert_by_ci",
    )
    if full_name:
        absorb_provisional(cur, person_id, full_name)
    return person_id, "created"


def _flag_dob_conflict(cur, person_id, stored, incoming) -> None:
    """A stored DOB is never overwritten by a row; a different one is queued for review."""
    if not stored or not incoming or stored == incoming:
        return
    ctx = provenance.current_source()
    provenance.open_review(
        cur,
        kind="dob_conflict",
        dedupe_key=f"dob_conflict:{person_id}:{provenance.value_hash(incoming)}",
        person_id=person_id,
        evidence={
            "stored_hash": provenance.value_hash(stored),
            "incoming_hash": provenance.value_hash(incoming),
            "source_kind": ctx[0] if ctx else None,
            "source_ref": ctx[1] if ctx else None,
        },
    )


def _fill_name_person(cur, person_id, birth_date, phone, address, key: str | None = None) -> None:
    cur.execute(
        "SELECT full_name, birth_date, phone, address FROM avila.person WHERE id = %s",
        (person_id,),
    )
    before = cur.fetchone() or {}
    _flag_dob_conflict(cur, person_id, before.get("birth_date"), birth_date)
    after = {
        **before,
        "birth_date": before.get("birth_date") or birth_date,
        "phone": phone or before.get("phone"),
        "address": address or before.get("address"),
    }
    cur.execute(
        """
        UPDATE avila.person SET
          provisional_key = coalesce(%s, provisional_key),
          birth_date = %s,
          phone = %s,
          address = %s,
          updated_at = now()
        WHERE id = %s
        """,
        (key, after["birth_date"], after["phone"], after["address"], person_id),
    )
    _record_person_changes(cur, person_id, before, after, "upsert_by_name")


def upsert_by_name(
    cur,
    *,
    full_name: str,
    birth_date=None,
    phone: str | None = None,
    address: str | None = None,
    dry_run: bool = False,
) -> tuple[str | None, str]:
    key = provisional_key_for_name(full_name)
    cur.execute("SELECT id FROM avila.person WHERE provisional_key = %s", (key,))
    row = cur.fetchone()
    if row:
        if not dry_run:
            _fill_name_person(cur, row["id"], birth_date, phone, address)
            absorb_provisional(cur, str(row["id"]), full_name)
        return str(row["id"]), "exists"

    # Reuse any existing name-only row (legacy invoice-scoped provisional keys).
    cur.execute(
        """
        SELECT id FROM avila.person
        WHERE identity_number IS NULL
          AND (name_folded = %s OR lower(full_name) = lower(%s))
        ORDER BY
          CASE WHEN provisional_key LIKE 'name:%%' THEN 0 ELSE 1 END,
          created_at
        LIMIT 1
        """,
        (fold_person_name(full_name), full_name),
    )
    row = cur.fetchone()
    if row:
        if not dry_run:
            _fill_name_person(cur, row["id"], birth_date, phone, address, key=key)
            absorb_provisional(cur, str(row["id"]), full_name)
        return str(row["id"]), "updated"

    if dry_run:
        return None, "dry_create"
    cur.execute(
        """
        INSERT INTO avila.person (
          identity_type, full_name, provisional_key, birth_date, phone, address
        ) VALUES ('unknown', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (full_name, key, birth_date, phone, address),
    )
    person_id = str(cur.fetchone()["id"])
    _record_person_changes(
        cur,
        person_id,
        {},
        {"full_name": full_name, "birth_date": birth_date, "phone": phone, "address": address},
        "upsert_by_name",
    )
    absorb_provisional(cur, person_id, full_name)
    return person_id, "created"


def upsert_titular(
    cur,
    *,
    full_name: str | None,
    identity_number: str | None,
    identity_type: str = "cedula",
) -> str | None:
    """Path/OCR titular helper used by the document loader."""
    if not full_name and not identity_number:
        return None
    if identity_number:
        person_id, _ = upsert_by_ci(
            cur,
            identity_number=identity_number,
            full_name=full_name,
            identity_type=identity_type,
        )
        return person_id
    assert full_name
    person_id, _ = upsert_by_name(cur, full_name=full_name)
    return person_id


def person_fields(cur, person_id: str) -> dict[str, Any]:
    cur.execute(
        f"SELECT {', '.join(PERSON_FIELDS)} FROM avila.person WHERE id = %s", (person_id,)
    )
    return cur.fetchone() or {}
