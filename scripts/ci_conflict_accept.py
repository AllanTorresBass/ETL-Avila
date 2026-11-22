#!/usr/bin/env python3
"""Accept open ``ci_conflict`` reviews the way Aceptar does in /revision.

  PYTHONPATH=scripts .venv/bin/python scripts/ci_conflict_accept.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/ci_conflict_accept.py --apply

The review's person becomes the factura titular (source ``review``). Any other
titular on that factura becomes beneficiario. Both role changes record field
provenance with rule ``review_promote_titular`` and the review id. Names,
cédulas, and other person fields are not touched. Stdout is counts only.
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

RESOLVER = "etl:ci_conflict_accept"
RULE = "review_promote_titular"


def run(cur) -> None:
    cur.execute(
        """
        SELECT r.id::text AS review_id, r.invoice_id::text AS invoice_id, r.person_id::text AS person_id,
               (SELECT ip.role::text FROM avila.invoice_person ip
                WHERE ip.invoice_id = r.invoice_id AND ip.person_id = r.person_id) AS current_role
        FROM avila.review_item r
        JOIN avila.person p ON p.id = r.person_id
        WHERE r.kind = 'ci_conflict' AND r.status = 'open' AND r.invoice_id IS NOT NULL
        """
    )
    reviews = cur.fetchall()
    accepted: list[str] = []
    for review in reviews:
        invoice_id, person_id = review["invoice_id"], review["person_id"]
        cur.execute(
            """
            UPDATE avila.invoice_person SET role = 'beneficiario', source = 'review'
            WHERE invoice_id = %s::uuid AND role = 'titular' AND person_id <> %s::uuid
            RETURNING person_id::text AS person_id
            """,
            (invoice_id, person_id),
        )
        for demoted in cur.fetchall():
            provenance.counters["titulars_demoted"] += 1
            provenance.record(
                cur,
                entity="invoice_person",
                entity_id=f"{invoice_id}:{demoted['person_id']}",
                field="role",
                old="titular",
                new="beneficiario",
                rule_id=RULE,
                source_kind="review",
                source_ref=f"review_item:{review['review_id']}",
            )
        cur.execute(
            """
            INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
            VALUES (%s::uuid, %s::uuid, 'titular', 'review')
            ON CONFLICT (invoice_id, person_id) DO UPDATE SET role = 'titular', source = 'review'
            """,
            (invoice_id, person_id),
        )
        if review["current_role"] != "titular":
            provenance.counters["persons_promoted"] += 1
        provenance.record(
            cur,
            entity="invoice_person",
            entity_id=f"{invoice_id}:{person_id}",
            field="role",
            old=review["current_role"],
            new="titular",
            rule_id=RULE,
            source_kind="review",
            source_ref=f"review_item:{review['review_id']}",
        )
        accepted.append(review["review_id"])

    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE id = ANY(%s::uuid[]) AND status = 'open'
        """,
        (RESOLVER, accepted),
    )
    provenance.counters["reviews_accepted"] = cur.rowcount
    cur.execute("SELECT count(*) AS n FROM avila.review_item WHERE kind = 'ci_conflict' AND status = 'open'")
    provenance.counters["reviews_still_open"] = cur.fetchone()["n"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "ci_conflict_accept", vars(args), apply=args.apply)
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
