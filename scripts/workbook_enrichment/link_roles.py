"""Link persons to invoices with titular / beneficiario roles."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provenance  # noqa: E402


def link_invoice_person(
    cur,
    *,
    invoice_id: str,
    person_id: str,
    role: str,
    parentesco: str | None = None,
    source: str = "workbook",
    dry_run: bool = False,
) -> str:
    if dry_run:
        return "dry_link"
    cur.execute(
        "SELECT role::text AS role FROM avila.invoice_person WHERE invoice_id = %s AND person_id = %s",
        (invoice_id, person_id),
    )
    prior = cur.fetchone()
    if role == "titular":
        # One titular per invoice — drop prior titular links for other persons
        cur.execute(
            """
            DELETE FROM avila.invoice_person
            WHERE invoice_id = %s AND role = 'titular' AND person_id <> %s
            """,
            (invoice_id, person_id),
        )
    cur.execute(
        """
        INSERT INTO avila.invoice_person (invoice_id, person_id, role, parentesco, source)
        VALUES (%s, %s, %s::avila.invoice_person_role, %s, %s)
        ON CONFLICT (invoice_id, person_id) DO UPDATE SET
          role = CASE
            WHEN avila.invoice_person.role = 'titular' AND EXCLUDED.role = 'beneficiario'
              THEN avila.invoice_person.role
            WHEN avila.invoice_person.role = 'unknown' THEN EXCLUDED.role
            WHEN EXCLUDED.role = 'titular' THEN EXCLUDED.role
            ELSE avila.invoice_person.role
          END,
          parentesco = coalesce(EXCLUDED.parentesco, avila.invoice_person.parentesco),
          source = coalesce(EXCLUDED.source, avila.invoice_person.source)
        """,
        (invoice_id, person_id, role, parentesco, source),
    )
    cur.execute(
        "SELECT role::text AS role FROM avila.invoice_person WHERE invoice_id = %s AND person_id = %s",
        (invoice_id, person_id),
    )
    provenance.record(
        cur,
        entity="invoice_person",
        entity_id=f"{invoice_id}:{person_id}",
        field="role",
        old=prior["role"] if prior else None,
        new=cur.fetchone()["role"],
        rule_id=f"workbook_{role}",
    )
    return "linked"


def apply_row_links(
    cur,
    *,
    invoice_id: str | None,
    people: dict[str, Any],
    row: dict[str, Any],
    dry_run: bool = False,
) -> list[str]:
    actions: list[str] = []
    if not invoice_id:
        return ["no_invoice"]
    titular_id = people.get("titular_id")
    beneficiario_id = people.get("beneficiario_id")
    if titular_id:
        actions.append(
            link_invoice_person(
                cur,
                invoice_id=invoice_id,
                person_id=titular_id,
                role="titular",
                parentesco="TITULAR" if not row.get("parentesco") else None,
                source="workbook",
                dry_run=dry_run,
            )
        )
    if beneficiario_id and beneficiario_id != titular_id:
        actions.append(
            link_invoice_person(
                cur,
                invoice_id=invoice_id,
                person_id=beneficiario_id,
                role="beneficiario",
                parentesco=row.get("parentesco"),
                source="workbook",
                dry_run=dry_run,
            )
        )
    elif beneficiario_id and beneficiario_id == titular_id and row.get("parentesco"):
        # Same person — store parentesco on titular link
        actions.append(
            link_invoice_person(
                cur,
                invoice_id=invoice_id,
                person_id=titular_id,
                role="titular",
                parentesco=row.get("parentesco"),
                source="workbook",
                dry_run=dry_run,
            )
        )
    return actions
