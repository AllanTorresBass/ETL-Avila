#!/usr/bin/env python3
"""Repair Aaron Matheus / Helber Matheus case graph after packet load.

- Merge AARONMATHEUS provisional into AARON MATHEUS
- Upsert Helber by CI 13996036
- Link Helber=titular, Aaron=beneficiario on target invoices
- Attach Helber person_id on cedula / carnet-like pages
- Relink authorization_line.invoice_id when FACT appears in source metadata
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_load import load_env  # noqa: E402
from person_upsert import upsert_by_ci  # noqa: E402

AARON_KEEP = "e93257b2-63aa-4d23-a958-912dbc97b477"
AARON_DUP = "40c06e22-ba55-47d2-bac7-951cb1552f51"
AARON_FACTS = ("7316", "7394", "7759", "7798", "7799")
HELBER_FACT = "8322"
HELBER_CI = "13996036"


def connect():
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL_UNPOOLED missing")
    return psycopg.connect(url, row_factory=dict_row)


def merge_aaron_dup(cur, *, apply: bool) -> dict:
    cur.execute("SELECT id, full_name FROM avila.person WHERE id = %s::uuid", (AARON_DUP,))
    dup = cur.fetchone()
    cur.execute("SELECT id, full_name, birth_date, notes FROM avila.person WHERE id = %s::uuid", (AARON_KEEP,))
    keep = cur.fetchone()
    stats = {"dup_exists": bool(dup), "keep_exists": bool(keep), "auth_moved": 0}
    if not keep:
        raise SystemExit(f"Aaron keep id missing: {AARON_KEEP}")
    if not dup:
        return stats
    if apply:
        cur.execute(
            "UPDATE avila.authorization_line SET person_id = %s WHERE person_id = %s",
            (AARON_KEEP, AARON_DUP),
        )
        stats["auth_moved"] = cur.rowcount
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
            (AARON_KEEP, AARON_DUP, AARON_KEEP),
        )
        cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s", (AARON_DUP,))
        cur.execute(
            "UPDATE avila.document SET person_id = %s WHERE person_id = %s",
            (AARON_KEEP, AARON_DUP),
        )
        cur.execute("DELETE FROM avila.person WHERE id = %s", (AARON_DUP,))
        cur.execute(
            """
            UPDATE avila.person SET
              notes = coalesce(notes || E'\n', '') ||
                'Patient on FACT 7316/7394/7759/7798/7799; titular CI on packets is Helber V-13996036.',
              updated_at = now()
            WHERE id = %s::uuid
              AND (notes IS NULL OR notes NOT LIKE '%%titular CI on packets is Helber%%')
            """,
            (AARON_KEEP,),
        )
    return stats


def upsert_helber(cur, *, apply: bool) -> tuple[str | None, str]:
    if not apply:
        cur.execute(
            """
            SELECT id FROM avila.person
            WHERE identity_type = 'cedula' AND identity_number = %s
            """,
            (HELBER_CI,),
        )
        row = cur.fetchone()
        return (str(row["id"]) if row else None), ("exists" if row else "dry_create")
    person_id, action = upsert_by_ci(
        cur,
        identity_number=HELBER_CI,
        full_name="HELBER JOSE MATHEUS ANDARA",
        identity_type="cedula",
        birth_date="1979-07-15",
    )
    if person_id:
        cur.execute(
            """
            UPDATE avila.person SET
              notes = %s,
              updated_at = now()
            WHERE id = %s::uuid
            """,
            (
                "BDV VP Servicios; carnet 20115 / C-20002997-6; titular on Aaron Matheus packets.",
                person_id,
            ),
        )
    return person_id, action


def ensure_7394_invoice_number(cur, *, apply: bool) -> str | None:
    """FACT 7394AARON… was inventoried without a number → synthetic path: key."""
    cur.execute("SELECT id::text FROM avila.invoice WHERE invoice_number = '7394'")
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(
        """
        SELECT i.id::text
        FROM avila.source_file sf
        JOIN avila.invoice i ON i.id = sf.invoice_id
        WHERE sf.backup_path ILIKE '%7394%AARON%MATHEUS%'
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    if apply:
        cur.execute(
            "UPDATE avila.invoice SET invoice_number = '7394' WHERE id = %s::uuid",
            (row["id"],),
        )
    return row["id"]


def link_roles(cur, helber_id: str, *, apply: bool) -> dict:
    ensure_7394_invoice_number(cur, apply=apply)
    facts = list(AARON_FACTS) + [HELBER_FACT]
    cur.execute(
        "SELECT id, invoice_number FROM avila.invoice WHERE invoice_number = ANY(%s)",
        (list(facts),),
    )
    invoices = cur.fetchall()
    stats = {"invoices": len(invoices), "links": 0}
    if not apply:
        return stats
    for inv in invoices:
        # Helber titular
        cur.execute(
            """
            INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
            VALUES (%s, %s, 'titular', 'repair_aaron_matheus_case')
            ON CONFLICT (invoice_id, person_id) DO UPDATE SET
              role = 'titular',
              source = EXCLUDED.source
            """,
            (inv["id"], helber_id),
        )
        # Aaron beneficiario on all six (patient on Aaron-named packets; also related on 8322)
        parentesco = "hijo" if inv["invoice_number"] in AARON_FACTS else None
        cur.execute(
            """
            INSERT INTO avila.invoice_person (invoice_id, person_id, role, parentesco, source)
            VALUES (%s, %s, 'beneficiario', %s, 'repair_aaron_matheus_case')
            ON CONFLICT (invoice_id, person_id) DO UPDATE SET
              role = 'beneficiario',
              parentesco = COALESCE(EXCLUDED.parentesco, avila.invoice_person.parentesco),
              source = EXCLUDED.source
            """,
            (inv["id"], AARON_KEEP, parentesco),
        )
        stats["links"] += 1
    return stats


def attach_helber_docs(cur, helber_id: str, *, apply: bool) -> dict:
    facts = list(AARON_FACTS) + [HELBER_FACT]
    cur.execute(
        """
        SELECT d.id, d.document_type::text, d.evidence, d.page_index, i.invoice_number
        FROM avila.document d
        JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE i.invoice_number = ANY(%s)
        """,
        (list(facts),),
    )
    docs = cur.fetchall()
    stats = {"scanned": len(docs), "cedula": 0, "carnet": 0}
    if not apply:
        return stats
    for d in docs:
        ev = (d["evidence"] or "").lower()
        dtype = d["document_type"]
        attach = False
        if dtype == "cedula_identidad":
            attach = True
            stats["cedula"] += 1
        elif "carnet" in ev or "bdv" in ev:
            attach = True
            stats["carnet"] += 1
        elif dtype == "otro_anexo" and ("13996036" in ev or "helber" in ev):
            attach = True
            stats["carnet"] += 1
        if attach:
            cur.execute(
                "UPDATE avila.document SET person_id = %s, updated_at = now() WHERE id = %s",
                (helber_id, d["id"]),
            )
    # Also attach by OCR-ish: any cedula on these invoices
    cur.execute(
        """
        UPDATE avila.document d
        SET person_id = %s, updated_at = now()
        FROM avila.invoice i
        WHERE d.invoice_id = i.id
          AND i.invoice_number = ANY(%s)
          AND d.document_type = 'cedula_identidad'
          AND (d.person_id IS NULL OR d.person_id <> %s::uuid)
        """,
        (helber_id, list(facts), helber_id),
    )
    return stats


def relink_auth(cur, *, apply: bool) -> dict:
    """Set invoice_id on Aaron auth lines when source_file / clave text contains FACT n."""
    cur.execute(
        """
        SELECT id, clave_rms, source_file, source_row, diagnosis
        FROM avila.authorization_line
        WHERE person_id = %s::uuid
        """,
        (AARON_KEEP,),
    )
    lines = cur.fetchall()
    cur.execute(
        "SELECT id, invoice_number FROM avila.invoice WHERE invoice_number = ANY(%s)",
        (list(AARON_FACTS) + [HELBER_FACT],),
    )
    by_num = {r["invoice_number"]: r["id"] for r in cur.fetchall()}
    stats = {"lines": len(lines), "linked": 0, "unmatched": 0}
    fact_re = re.compile(r"\bFACT(?:URA)?\s*0*(\d{3,6})\b", re.I)
    for line in lines:
        blob = " ".join(
            str(x or "") for x in (line["clave_rms"], line["source_file"], line["source_row"], line["diagnosis"])
        )
        m = fact_re.search(blob)
        inv_id = None
        if m:
            num = str(int(m.group(1)))  # strip zeros
            inv_id = by_num.get(num)
        if inv_id:
            stats["linked"] += 1
            if apply:
                cur.execute(
                    "UPDATE avila.authorization_line SET invoice_id = %s WHERE id = %s AND invoice_id IS NULL",
                    (inv_id, line["id"]),
                )
        else:
            stats["unmatched"] += 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    apply = args.apply
    with connect() as conn:
        with conn.cursor() as cur:
            print("merge", merge_aaron_dup(cur, apply=apply))
            helber_id, action = upsert_helber(cur, apply=apply)
            print("helber", helber_id, action)
            if not helber_id and apply:
                raise SystemExit("Helber upsert failed")
            if helber_id:
                print("roles", link_roles(cur, helber_id, apply=apply))
                print("docs", attach_helber_docs(cur, helber_id, apply=apply))
            print("auth", relink_auth(cur, apply=apply))
        if apply:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("dry-run only")


if __name__ == "__main__":
    main()
