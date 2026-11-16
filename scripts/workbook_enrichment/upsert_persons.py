"""Create / merge avila.person rows from canonical workbook fields."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from person_upsert import upsert_by_ci, upsert_by_name  # noqa: E402


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
    return upsert_by_ci(
        cur,
        identity_number=identity_number,
        full_name=full_name,
        birth_date=birth_date,
        phone=phone,
        address=address,
        dry_run=dry_run,
    )


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
    _ = invoice_number  # legacy arg; keys are name-scoped now
    return upsert_by_name(
        cur,
        full_name=full_name,
        birth_date=birth_date,
        phone=phone,
        address=address,
        dry_run=dry_run,
    )


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
