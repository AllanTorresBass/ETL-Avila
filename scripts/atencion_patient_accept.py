#!/usr/bin/env python3
"""Accept open ``atencion_patient`` reviews that carry a suggested person.

  PYTHONPATH=scripts .venv/bin/python scripts/atencion_patient_accept.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/atencion_patient_accept.py --apply

The same effects as Aceptar in /revision: the atención gets the review's
person, ``person_link_rule = 'review'``, and ``link_status`` complete when the
médico and especialidad are known (partial otherwise). Each link records field
provenance and the review closes with ``resolved_by = etl:atencion_patient_accept``.
Reviews with no suggested person stay open unless ``--reject-no-suggestion``
closes them as rejected (no data change, like Rechazar). An atención that a person already
linked keeps its patient. Stdout is counts only.
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

RESOLVER = "etl:atencion_patient_accept"


def link_atenciones(cur) -> list[str]:
    cur.execute(
        """
        SELECT r.id::text AS review_id, r.atencion_id::text AS atencion_id, r.person_id::text AS person_id,
               a.person_id::text AS current_person,
               EXISTS (
                 SELECT 1 FROM avila.invoice_person ip
                 WHERE ip.invoice_id = a.invoice_id AND ip.person_id = r.person_id
               ) AS on_same_invoice
        FROM avila.review_item r
        JOIN avila.atencion a ON a.id = r.atencion_id
        WHERE r.kind = 'atencion_patient' AND r.status = 'open' AND r.person_id IS NOT NULL
        """
    )
    reviews = cur.fetchall()
    cur.execute(
        """
        SELECT count(*) AS n FROM avila.review_item
        WHERE kind = 'atencion_patient' AND status = 'open' AND person_id IS NULL
        """
    )
    provenance.counters["held_no_suggestion"] = cur.fetchone()["n"]

    accepted: list[str] = []
    for review in reviews:
        if review["current_person"] and review["current_person"] != review["person_id"]:
            provenance.counters["held_atencion_already_linked"] += 1
            continue
        provenance.counters["person_on_same_invoice" if review["on_same_invoice"] else "person_on_other_invoice"] += 1
        cur.execute(
            """
            UPDATE avila.atencion SET
              person_id = %s::uuid,
              person_link_rule = 'review',
              link_status = CASE
                WHEN medico_id IS NOT NULL AND especialidad_id IS NOT NULL THEN 'complete'
                ELSE 'partial'
              END,
              updated_at = now()
            WHERE id = %s::uuid
            """,
            (review["person_id"], review["atencion_id"]),
        )
        provenance.record(
            cur,
            entity="atencion",
            entity_id=review["atencion_id"],
            field="person_id",
            old=review["current_person"],
            new=review["person_id"],
            rule_id="review_atencion_patient",
            source_kind="review",
            source_ref=f"review_item:{review['review_id']}",
        )
        accepted.append(review["review_id"])
    return accepted


def close_reviews(cur, accepted: list[str]) -> None:
    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE id = ANY(%s::uuid[]) AND status = 'open'
        RETURNING id
        """,
        (RESOLVER, accepted),
    )
    provenance.counters["reviews_accepted"] = len(cur.fetchall())


def reject_no_suggestion(cur) -> None:
    cur.execute(
        """
        UPDATE avila.review_item SET status = 'rejected', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE kind = 'atencion_patient' AND status = 'open' AND person_id IS NULL
        RETURNING id
        """,
        (RESOLVER,),
    )
    provenance.counters["reviews_rejected_no_suggestion"] = len(cur.fetchall())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--reject-no-suggestion",
        action="store_true",
        help="Close reviews with no suggested person as rejected, like Rechazar in /revision",
    )
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "atencion_patient_accept", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.pipeline(), conn.cursor() as cur:
            accepted = link_atenciones(cur)
        with conn.cursor() as cur:
            close_reviews(cur, accepted)
            if args.reject_no_suggestion:
                reject_no_suggestion(cur)
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
