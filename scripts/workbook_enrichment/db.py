"""Database helpers for workbook enrichment."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from env_load import load_env  # noqa: E402


def connect():
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL_UNPOOLED missing from .env")
    return psycopg.connect(url, row_factory=dict_row)


def find_invoice_id(cur, invoice_number: str | None) -> str | None:
    if not invoice_number:
        return None
    candidates = [invoice_number]
    # Tolerate zero-padded workbook values vs unpadded Neon keys.
    if invoice_number.isdigit():
        stripped = str(int(invoice_number))
        if stripped not in candidates:
            candidates.append(stripped)
        padded = invoice_number.zfill(6)
        if padded not in candidates:
            candidates.append(padded)
    cur.execute(
        "SELECT id FROM avila.invoice WHERE invoice_number = ANY(%s)",
        (candidates,),
    )
    row = cur.fetchone()
    return row["id"] if row else None
