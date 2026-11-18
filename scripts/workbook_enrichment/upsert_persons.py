"""Create / merge avila.person rows from canonical workbook fields."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contact_extract import canonical_phone, clean_address, phones_in_text  # noqa: E402
from person_upsert import fold_person_name, upsert_by_ci, upsert_by_name  # noqa: E402


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


def _is_titular_label(parentesco: str | None) -> bool:
    return bool(parentesco) and fold_person_name(parentesco) in {"titular", "el titular", "mismo"}


def row_is_titular_self(row: dict[str, Any]) -> bool:
    """The beneficiary on this row is the titular (same CI, same name, or PARENTESCO TITULAR)."""
    if row.get("titular_ci") and row.get("beneficiario_ci"):
        return row["titular_ci"] == row["beneficiario_ci"]
    names_match = bool(
        row.get("titular_name")
        and row.get("beneficiario_name")
        and fold_person_name(row["titular_name"]) == fold_person_name(row["beneficiario_name"])
    )
    if names_match and not row.get("beneficiario_ci"):
        return True
    no_other = not row.get("beneficiario_name") and not row.get("beneficiario_ci")
    return _is_titular_label(row.get("parentesco")) and (names_match or no_other)


def _person_key(ci: str | None, name: str | None) -> tuple[str, str] | None:
    if ci:
        return ("ci", ci)
    if name:
        return ("name", fold_person_name(name))
    return None


def _cell_phone(value: str | None) -> str | None:
    """Prefer a mobile in the cell, otherwise the first landline."""
    numbers = phones_in_text(value)
    mobiles = [number for number in numbers if number[1] == "4"]
    if mobiles:
        return mobiles[0]
    return numbers[0] if numbers else canonical_phone(value)


def contact_assignments(row: dict[str, Any]) -> list[tuple[tuple[str, str], str, str]]:
    """Phone and address owners for one workbook row.

    Household phone and address stay on the titular. The emergency-contact
    column is the only phone that belongs to the beneficiario. A household
    number that the old mapping wrote onto a different beneficiario is returned
    as ``phone_clear_if`` so a repair can remove that copy when it still matches.
    """
    titular = _person_key(row.get("titular_ci"), row.get("titular_name"))
    beneficiario = _person_key(row.get("beneficiario_ci"), row.get("beneficiario_name"))
    same = row_is_titular_self(row)
    out: list[tuple[tuple[str, str], str, str]] = []
    phone = _cell_phone(row.get("phone"))
    address = clean_address(row.get("address"), min_len=4)
    if titular and phone:
        out.append((titular, "phone", phone))
    if titular and address:
        out.append((titular, "address", address))
    emergency = _cell_phone(row.get("beneficiario_phone"))
    target = titular if same else beneficiario
    if target and emergency and emergency != phone:
        out.append((target, "phone", emergency))
    if not same and beneficiario and phone and phone != emergency:
        out.append((beneficiario, "phone_clear_if", phone))
    return out


def titular_birth_date(row: dict[str, Any], *, same_person: bool):
    """DOB to write on the titular: its own column, else the beneficiary column when that is the titular."""
    if row.get("birth_date"):
        return row["birth_date"]
    if same_person:
        return row.get("beneficiario_birth_date")
    return None


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

    phone = _cell_phone(row.get("phone"))
    address = clean_address(row.get("address"), min_len=4)
    emergency = _cell_phone(row.get("beneficiario_phone"))
    same_person = row_is_titular_self(row)
    titular_birth = titular_birth_date(row, same_person=same_person)

    if row.get("titular_ci"):
        titular_id, act = upsert_person_by_ci(
            cur,
            identity_number=row["titular_ci"],
            full_name=row.get("titular_name"),
            birth_date=titular_birth,
            phone=phone,
            address=address,
            dry_run=dry_run,
        )
        actions.append(f"titular:{act}")
    elif row.get("titular_name"):
        titular_id, act = upsert_person_by_name(
            cur,
            full_name=row["titular_name"],
            birth_date=titular_birth,
            phone=phone,
            address=address,
            invoice_number=row.get("invoice_number"),
            dry_run=dry_run,
        )
        actions.append(f"titular:{act}")

    if same_person:
        beneficiario_id = titular_id
        actions.append("beneficiario:same_as_titular")
    elif row.get("beneficiario_ci"):
        beneficiario_id, act = upsert_person_by_ci(
            cur,
            identity_number=row["beneficiario_ci"],
            full_name=row.get("beneficiario_name"),
            birth_date=row.get("beneficiario_birth_date"),
            phone=emergency,
            address=None,
            dry_run=dry_run,
        )
        actions.append(f"beneficiario:{act}")
    elif row.get("beneficiario_name"):
        beneficiario_id, act = upsert_person_by_name(
            cur,
            full_name=row["beneficiario_name"],
            birth_date=row.get("beneficiario_birth_date"),
            phone=emergency,
            address=None,
            invoice_number=row.get("invoice_number"),
            dry_run=dry_run,
        )
        actions.append(f"beneficiario:{act}")

    return {
        "titular_id": titular_id,
        "beneficiario_id": beneficiario_id,
        "actions": actions,
    }
