"""Upsert avila.authorization_line rows from canonical workbook rows."""

from __future__ import annotations

import hashlib
from typing import Any


def source_row_key(sheet: str, row_number: int) -> str:
    return f"{sheet}:{row_number}"


def line_hash(
    *,
    source_file: str,
    source_row: str,
    clave_rms: str | None,
    invoice_number: str | None,
) -> str:
    raw = "|".join(
        [
            source_file,
            source_row,
            clave_rms or "",
            invoice_number or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def upsert_authorization_line(
    cur,
    *,
    row: dict[str, Any],
    source_file: str,
    sheet: str,
    row_number: int,
    invoice_id: str | None,
    person_id: str | None,
    dry_run: bool = False,
) -> str:
    source_row = source_row_key(sheet, row_number)
    digest = line_hash(
        source_file=source_file,
        source_row=source_row,
        clave_rms=row.get("clave_rms"),
        invoice_number=row.get("invoice_number"),
    )
    if dry_run:
        return "dry_line"

    # Optionally enrich invoice control/issue when we have a match
    if invoice_id and (row.get("control_number") or row.get("issue_date")):
        cur.execute(
            """
            UPDATE avila.invoice SET
              control_number = coalesce(%s, control_number),
              issue_date = coalesce(%s, issue_date)
            WHERE id = %s
            """,
            (row.get("control_number"), row.get("issue_date"), invoice_id),
        )

    cur.execute(
        """
        INSERT INTO avila.authorization_line (
          invoice_id, person_id, clave_rms, contratante,
          service_date, request_date, diagnosis, service_description,
          provider_name, provider_rif,
          amount_bs, amount_usd, coverage_amount, authorized_amount,
          source_file, source_row, source_hash
        ) VALUES (
          %s, %s, %s, %s,
          %s, %s, %s, %s,
          %s, %s,
          %s, %s, %s, %s,
          %s, %s, %s
        )
        ON CONFLICT (source_hash) DO UPDATE SET
          invoice_id = coalesce(EXCLUDED.invoice_id, avila.authorization_line.invoice_id),
          person_id = coalesce(EXCLUDED.person_id, avila.authorization_line.person_id),
          clave_rms = coalesce(EXCLUDED.clave_rms, avila.authorization_line.clave_rms),
          contratante = coalesce(EXCLUDED.contratante, avila.authorization_line.contratante),
          service_date = coalesce(EXCLUDED.service_date, avila.authorization_line.service_date),
          request_date = coalesce(EXCLUDED.request_date, avila.authorization_line.request_date),
          diagnosis = coalesce(EXCLUDED.diagnosis, avila.authorization_line.diagnosis),
          service_description = coalesce(
            EXCLUDED.service_description, avila.authorization_line.service_description
          ),
          provider_name = coalesce(EXCLUDED.provider_name, avila.authorization_line.provider_name),
          provider_rif = coalesce(EXCLUDED.provider_rif, avila.authorization_line.provider_rif),
          amount_bs = coalesce(EXCLUDED.amount_bs, avila.authorization_line.amount_bs),
          amount_usd = coalesce(EXCLUDED.amount_usd, avila.authorization_line.amount_usd),
          coverage_amount = coalesce(
            EXCLUDED.coverage_amount, avila.authorization_line.coverage_amount
          ),
          authorized_amount = coalesce(
            EXCLUDED.authorized_amount, avila.authorization_line.authorized_amount
          ),
          updated_at = now()
        """,
        (
            invoice_id,
            person_id,
            row.get("clave_rms"),
            row.get("contratante"),
            row.get("service_date"),
            row.get("request_date"),
            row.get("diagnosis"),
            row.get("service_description"),
            row.get("provider_name"),
            row.get("provider_rif"),
            row.get("amount_bs"),
            row.get("amount_usd"),
            row.get("coverage_amount"),
            row.get("authorized_amount"),
            source_file,
            source_row,
            digest,
        ),
    )
    return "upserted"
