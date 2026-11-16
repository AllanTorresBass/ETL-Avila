"""Shared avila.person upsert + provisional absorb (path loader and workbooks)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


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


def absorb_provisional(cur, survivor_id: str, full_name: str) -> int:
    """Rewire links from same-name provisional rows into survivor; return absorbed count."""
    if not full_name:
        return 0
    cur.execute(
        """
        SELECT id FROM avila.person
        WHERE id <> %s::uuid
          AND identity_number IS NULL
          AND provisional_key IS NOT NULL
          AND lower(full_name) = lower(%s)
        """,
        (survivor_id, full_name),
    )
    orphans = cur.fetchall()
    for orphan in orphans:
        oid = orphan["id"]
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
            (survivor_id, oid, survivor_id),
        )
        cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s", (oid,))
        cur.execute(
            "UPDATE avila.document SET person_id = %s WHERE person_id = %s",
            (survivor_id, oid),
        )
        cur.execute(
            "UPDATE avila.authorization_line SET person_id = %s WHERE person_id = %s",
            (survivor_id, oid),
        )
        cur.execute("DELETE FROM avila.person WHERE id = %s", (oid,))
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
        new_name = _merge_text(row["full_name"], full_name)
        cur.execute(
            """
            UPDATE avila.person SET
              full_name = coalesce(%s, full_name),
              birth_date = coalesce(%s, birth_date),
              phone = coalesce(%s, phone),
              address = coalesce(%s, address),
              updated_at = now()
            WHERE id = %s
            """,
            (
                new_name,
                row["birth_date"] or birth_date,
                _merge_text(row["phone"], phone),
                _merge_text(row["address"], address),
                row["id"],
            ),
        )
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
    if full_name:
        absorb_provisional(cur, person_id, full_name)
    return person_id, "created"


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
            cur.execute(
                """
                UPDATE avila.person SET
                  birth_date = coalesce(%s, birth_date),
                  phone = coalesce(%s, phone),
                  address = coalesce(%s, address),
                  updated_at = now()
                WHERE id = %s
                """,
                (birth_date, phone, address, row["id"]),
            )
            absorb_provisional(cur, str(row["id"]), full_name)
        return str(row["id"]), "exists"

    # Reuse any existing name-only row (legacy invoice-scoped provisional keys).
    cur.execute(
        """
        SELECT id FROM avila.person
        WHERE identity_number IS NULL
          AND lower(full_name) = lower(%s)
        ORDER BY
          CASE WHEN provisional_key LIKE 'name:%%' THEN 0 ELSE 1 END,
          created_at
        LIMIT 1
        """,
        (full_name,),
    )
    row = cur.fetchone()
    if row:
        if not dry_run:
            cur.execute(
                """
                UPDATE avila.person SET
                  provisional_key = %s,
                  birth_date = coalesce(%s, birth_date),
                  phone = coalesce(%s, phone),
                  address = coalesce(%s, address),
                  updated_at = now()
                WHERE id = %s
                """,
                (key, birth_date, phone, address, row["id"]),
            )
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
