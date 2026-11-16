"""Create / merge avila.person rows from canonical workbook fields."""

from __future__ import annotations

from typing import Any


def _merge_text(cur_val: str | None, new_val: str | None) -> str | None:
    if new_val and not cur_val:
        return new_val
    if new_val and cur_val and len(new_val) > len(cur_val):
        return new_val
    return cur_val


def upsert_person_by_ci(
    cur,
    *,
    identity_number: str,
    full_name: str | None = None,
    birth_date=None,
    phone: str | None = None,
    address: str | None = None,
    dry_run: bool = False,
) -> tuple[str | None, str]:
    """Return (person_id, action) where action is created|updated|exists|dry."""
    cur.execute(
        """
        SELECT id, full_name, birth_date, phone, address, provisional_key
        FROM avila.person
        WHERE identity_type = 'cedula' AND identity_number = %s
        """,
        (identity_number,),
    )
    row = cur.fetchone()
    if row:
        if dry_run:
            return row["id"], "exists"
        new_name = _merge_text(row["full_name"], full_name)
        new_phone = _merge_text(row["phone"], phone)
        new_address = _merge_text(row["address"], address)
        new_birth = row["birth_date"] or birth_date
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
            (new_name, new_birth, new_phone, new_address, row["id"]),
        )
        # Merge provisional same-name rows into this CI person when possible
        if full_name:
            _absorb_provisional(cur, row["id"], full_name)
        return row["id"], "updated"

    if dry_run:
        return None, "dry_create"
    cur.execute(
        """
        INSERT INTO avila.person (
          identity_type, identity_number, full_name, birth_date, phone, address
        ) VALUES ('cedula', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (identity_number, full_name, birth_date, phone, address),
    )
    person_id = cur.fetchone()["id"]
    if full_name:
        _absorb_provisional(cur, person_id, full_name)
    return person_id, "created"


def upsert_person_by_name(
    cur,
    *,
    full_name: str,
    birth_date=None,
    phone: str | None = None,
    address: str | None = None,
    invoice_number: str | None = None,
    dry_run: bool = False,
) -> tuple[str | None, str]:
    key = f"titular:{invoice_number or 'wb'}:{full_name.casefold()}"
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
        return row["id"], "exists"
    # Prefer existing named person without CI
    cur.execute(
        """
        SELECT id FROM avila.person
        WHERE identity_number IS NULL
          AND lower(full_name) = lower(%s)
        ORDER BY created_at
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
                  provisional_key = coalesce(provisional_key, %s),
                  birth_date = coalesce(%s, birth_date),
                  phone = coalesce(%s, phone),
                  address = coalesce(%s, address),
                  updated_at = now()
                WHERE id = %s
                """,
                (key, birth_date, phone, address, row["id"]),
            )
        return row["id"], "updated"
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
    return cur.fetchone()["id"], "created"


def _absorb_provisional(cur, person_id: str, full_name: str) -> None:
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
        cur.execute(
            "UPDATE avila.authorization_line SET person_id = %s WHERE person_id = %s",
            (person_id, orphan["id"]),
        )
        cur.execute("DELETE FROM avila.person WHERE id = %s", (orphan["id"],))


def resolve_people_from_row(
    cur,
    row: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Return {titular_id, beneficiario_id, actions[]}."""
    actions: list[str] = []
    titular_id = None
    beneficiario_id = None

    # Contact prefers beneficiary phone/address when present (emergency contact forms)
    phone = row.get("phone")
    address = row.get("address")

    if row.get("titular_ci"):
        titular_id, act = upsert_person_by_ci(
            cur,
            identity_number=row["titular_ci"],
            full_name=row.get("titular_name"),
            birth_date=row.get("birth_date"),
            phone=phone if not row.get("beneficiario_ci") else None,
            address=address if not row.get("beneficiario_ci") else None,
            dry_run=dry_run,
        )
        actions.append(f"titular:{act}")
    elif row.get("titular_name"):
        titular_id, act = upsert_person_by_name(
            cur,
            full_name=row["titular_name"],
            birth_date=row.get("birth_date"),
            phone=phone if not row.get("beneficiario_name") else None,
            address=address if not row.get("beneficiario_name") else None,
            invoice_number=row.get("invoice_number"),
            dry_run=dry_run,
        )
        actions.append(f"titular:{act}")

    same_person = (
        row.get("titular_ci")
        and row.get("beneficiario_ci")
        and row["titular_ci"] == row["beneficiario_ci"]
    ) or (
        row.get("titular_name")
        and row.get("beneficiario_name")
        and row["titular_name"].casefold() == row["beneficiario_name"].casefold()
        and not row.get("beneficiario_ci")
    )

    if same_person:
        beneficiario_id = titular_id
        actions.append("beneficiario:same_as_titular")
    elif row.get("beneficiario_ci"):
        beneficiario_id, act = upsert_person_by_ci(
            cur,
            identity_number=row["beneficiario_ci"],
            full_name=row.get("beneficiario_name"),
            birth_date=row.get("beneficiario_birth_date") or row.get("birth_date"),
            phone=phone,
            address=address,
            dry_run=dry_run,
        )
        actions.append(f"beneficiario:{act}")
    elif row.get("beneficiario_name"):
        beneficiario_id, act = upsert_person_by_name(
            cur,
            full_name=row["beneficiario_name"],
            birth_date=row.get("beneficiario_birth_date") or row.get("birth_date"),
            phone=phone,
            address=address,
            invoice_number=row.get("invoice_number"),
            dry_run=dry_run,
        )
        actions.append(f"beneficiario:{act}")

    return {
        "titular_id": titular_id,
        "beneficiario_id": beneficiario_id,
        "actions": actions,
    }
