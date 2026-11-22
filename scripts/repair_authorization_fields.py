#!/usr/bin/env python3
"""Store each authorization line's insurer (account_id) and normalized provider_code.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_authorization_fields.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/repair_authorization_fields.py --apply

The insurer comes from the workbook folder, the same rule match_auth_lines uses
(``line_account``). The provider code folds spellings such as ``G.P.S. Ávila``
and ``GPS AVILA`` into ``gps_avila``. Rerun after each workbook load. Only
changed fields are written, each with field provenance. Stdout is counts only.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from match_auth_lines import line_account  # noqa: E402
from workbook_enrichment.normalize import provider_code  # noqa: E402

RULE = "authorization_fields"


def run(cur, counts: Counter) -> None:
    cur.execute("SELECT id::text AS id, code FROM avila.account")
    account_ids = {row["code"]: row["id"] for row in cur.fetchall()}
    cur.execute(
        """
        SELECT id::text AS id, source_file, provider_name,
               account_id::text AS account_id, provider_code
        FROM avila.authorization_line
        """
    )
    accounts_by_file: dict[str, str | None] = {}
    for line in cur.fetchall():
        source = line["source_file"]
        if source not in accounts_by_file:
            accounts_by_file[source] = account_ids.get(line_account(source) or "")
        wanted = {"account_id": accounts_by_file[source], "provider_code": provider_code(line["provider_name"])}
        counts["account_known" if wanted["account_id"] else "account_unknown"] += 1
        counts[f"provider_{wanted['provider_code'] or 'none'}"] += 1
        changes = {field: (line[field], value) for field, value in wanted.items() if line[field] != value}
        if not changes:
            continue
        counts["lines_changed"] += 1
        cur.execute(
            """
            UPDATE avila.authorization_line
            SET account_id = %s::uuid, provider_code = %s, updated_at = now()
            WHERE id = %s::uuid
            """,
            (wanted["account_id"], wanted["provider_code"], line["id"]),
        )
        for field, (old, new) in changes.items():
            provenance.record(
                cur,
                entity="authorization_line",
                entity_id=line["id"],
                field=field,
                old=old,
                new=new,
                rule_id=RULE,
                source_kind="path" if field == "account_id" else "workbook",
                source_ref=source,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "repair_authorization_fields", vars(args), apply=args.apply)
    counts: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn:
        with conn.pipeline(), conn.cursor() as cur:
            run(cur, counts)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(counts))
    print("apply" if args.apply else "dry-run", dict(sorted(counts.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
