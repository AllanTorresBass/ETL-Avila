#!/usr/bin/env python3
"""Merge ``duplicate_candidate`` pairs whose cédulas differ by one digit.

  PYTHONPATH=scripts .venv/bin/python scripts/person_dup_merge.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/person_dup_merge.py --apply

A pair merges only when the two names refer to the same person, the cédulas
have the same length and differ in one digit, and one side has more facturas.
That side survives and keeps its cédula: that number is the one tied to the
facturas. A tie stays open. The other side's facturas, documents,
authorizations, atenciones, services, and reviews move to the survivor, its
empty contact fields fill the survivor's empty fields, and its row is removed.
Provenance records ``merged_from``, the discarded cédula hash, and each filled
field. Other pairs stay open. Stdout is counts only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from especialidad_normalize import osa_distance  # noqa: E402
from upload_documents_to_blob import _names_refer_to_same_person  # noqa: E402

RESOLVER = "etl:person_dup_merge"
RULE = "review_merge_person_one_digit"
FILL_FIELDS = ("full_name", "birth_date", "phone", "address")

PERSON_SQL = """
SELECT p.id::text AS id, p.identity_number, p.full_name, p.birth_date, p.phone, p.address,
       (SELECT count(*) FROM avila.invoice_person ip WHERE ip.person_id = p.id)::int AS invoices
FROM avila.person p WHERE p.id = %s::uuid
"""


def one_digit(a: str | None, b: str | None) -> bool:
    return bool(a and b and a != b and len(a) == len(b) and osa_distance(a, b, 2) == 1)


def merge(cur, survivor: dict, alias: dict, review_id: str) -> None:
    s, a = survivor["id"], alias["id"]
    cur.execute(
        """
        UPDATE avila.invoice_person s
        SET role = x.role, parentesco = coalesce(s.parentesco, x.parentesco), source = x.source
        FROM avila.invoice_person x
        WHERE x.person_id = %s::uuid AND s.person_id = %s::uuid
          AND s.invoice_id = x.invoice_id AND s.role = 'unknown' AND x.role <> 'unknown'
        """,
        (a, s),
    )
    cur.execute(
        """
        UPDATE avila.invoice_person SET person_id = %s::uuid
        WHERE person_id = %s::uuid AND NOT EXISTS (
          SELECT 1 FROM avila.invoice_person y
          WHERE y.invoice_id = avila.invoice_person.invoice_id AND y.person_id = %s::uuid)
        """,
        (s, a, s),
    )
    provenance.counters["invoice_links_moved"] += cur.rowcount
    cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s::uuid", (a,))
    for statement in (
        "UPDATE avila.document SET person_id = %s::uuid WHERE person_id = %s::uuid",
        "UPDATE avila.authorization_line SET person_id = %s::uuid WHERE person_id = %s::uuid",
        "UPDATE avila.atencion SET person_id = %s::uuid WHERE person_id = %s::uuid",
        "UPDATE avila.invoice_service SET person_id = %s::uuid WHERE person_id = %s::uuid",
        "UPDATE avila.review_item SET person_id = %s::uuid WHERE person_id = %s::uuid",
        "UPDATE avila.review_item SET other_person_id = %s::uuid WHERE other_person_id = %s::uuid",
    ):
        cur.execute(statement, (s, a))
    cur.execute("DELETE FROM avila.person WHERE id = %s::uuid", (a,))
    cur.execute(
        """
        UPDATE avila.person SET
          full_name = coalesce(nullif(full_name, ''), %s),
          birth_date = coalesce(birth_date, %s::date),
          phone = coalesce(nullif(phone, ''), %s),
          address = coalesce(nullif(address, ''), %s),
          updated_at = now()
        WHERE id = %s::uuid
        """,
        (alias["full_name"], alias["birth_date"], alias["phone"], alias["address"], s),
    )
    ref = f"review_item:{review_id}"
    for field in FILL_FIELDS:
        if not survivor[field] and alias[field]:
            provenance.counters[f"filled_{field}"] += 1
            provenance.record(
                cur, entity="person", entity_id=s, field=field, old=None, new=alias[field],
                rule_id=RULE, source_kind="review", source_ref=ref,
            )
    provenance.record(
        cur, entity="person", entity_id=s, field="merged_from", old=None, new=a,
        rule_id=RULE, source_kind="review", source_ref=ref,
    )
    provenance.record(
        cur, entity="person", entity_id=s, field="discarded_identity_number", old=None,
        new=alias["identity_number"], rule_id=RULE, source_kind="review", source_ref=ref,
        reason="one_digit_cedula_kept_invoice_side",
    )


def run(cur) -> None:
    cur.execute(
        """
        SELECT id::text AS review_id, person_id::text AS a, other_person_id::text AS b
        FROM avila.review_item
        WHERE kind = 'duplicate_candidate' AND status = 'open'
          AND person_id IS NOT NULL AND other_person_id IS NOT NULL
        """
    )
    reviews = cur.fetchall()
    merged: list[str] = []
    for review in reviews:
        cur.execute(PERSON_SQL, (review["a"],))
        a = cur.fetchone()
        cur.execute(PERSON_SQL, (review["b"],))
        b = cur.fetchone()
        if not a or not b:
            provenance.counters["held_person_missing"] += 1
            continue
        if not (a["full_name"] and b["full_name"] and _names_refer_to_same_person(a["full_name"], b["full_name"])):
            provenance.counters["held_name_differs"] += 1
            continue
        if not one_digit(a["identity_number"], b["identity_number"]):
            provenance.counters["held_not_one_digit"] += 1
            continue
        if a["invoices"] == b["invoices"]:
            provenance.counters["held_same_invoice_count"] += 1
            continue
        survivor, alias = (a, b) if a["invoices"] > b["invoices"] else (b, a)
        if alias["invoices"]:
            provenance.counters["merged_both_had_facturas"] += 1
        merge(cur, survivor, alias, review["review_id"])
        merged.append(review["review_id"])

    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE id = ANY(%s::uuid[]) AND status = 'open'
        """,
        (RESOLVER, merged),
    )
    provenance.counters["reviews_accepted"] = cur.rowcount
    provenance.counters["persons_merged"] = len(merged)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "person_dup_merge", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        run(cur)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url)
    counts = {k: v for k, v in sorted(provenance.counters.items()) if not k.startswith("prov:")}
    print("apply" if args.apply else "dry-run", counts, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
