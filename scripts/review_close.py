#!/usr/bin/env python3
"""Close every open review of one kind whose Aceptar changes no data.

  PYTHONPATH=scripts .venv/bin/python scripts/review_close.py --kind address_conflict           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/review_close.py --kind address_conflict --apply

For these kinds Aceptar in /revision only confirms the stored value and ignores
the other source, so closing them here matches the reader. Kinds whose Aceptar
merges or links records are refused. Stdout is counts only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402

RESOLVER = "etl:review_close"
NO_EFFECT_KINDS = ("address_conflict", "phone_conflict", "dob_conflict", "medico_mpps_conflict", "segment_review")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--kind", required=True, choices=NO_EFFECT_KINDS)
    parser.add_argument("--decision", choices=("accepted", "rejected"), default="accepted")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "review_close", vars(args), apply=args.apply)
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE avila.review_item SET status = %s, resolved_by = %s, resolved_at = now(), updated_at = now()
            WHERE kind = %s AND status = 'open'
            """,
            (args.decision, RESOLVER, args.kind),
        )
        provenance.counters[f"{args.kind}_{args.decision}"] = cur.rowcount
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url)
    print("apply" if args.apply else "dry-run", dict(provenance.counters), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
