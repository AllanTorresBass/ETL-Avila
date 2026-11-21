#!/usr/bin/env python3
"""Clear OCR junk stored as person.full_name (nationality, labels, dates).

Does not delete people. Clears unusable names; detaches date-like false CIs from
being treated as cédula by moving them to identity_type unknown when safe.

  PYTHONPATH=scripts .venv/bin/python scripts/cleanup_junk_person_names.py
  PYTHONPATH=scripts .venv/bin/python scripts/cleanup_junk_person_names.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from person_name_gate import is_date_like_identity, sanitize_person_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, "cleanup_junk_person_names", vars(args), apply=args.apply)
    stats: Counter = Counter()

    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id, full_name, identity_number, identity_type::text AS identity_type
            FROM avila.person
            WHERE coalesce(full_name, '') <> ''
               OR coalesce(identity_number, '') <> ''
            """
        )
        for row in cur.fetchall():
            name = row["full_name"]
            ci = row["identity_number"]
            cleaned = sanitize_person_name(name) if name else None
            needs_name_fix = bool(name) and cleaned != name
            date_ci = is_date_like_identity(ci)

            if needs_name_fix:
                stats["junk_name_candidates"] += 1
                if args.apply:
                    with provenance.source("derived", f"cleanup_junk_name:{row['id']}"):
                        cur.execute(
                            """
                            UPDATE avila.person
                            SET full_name = %s, updated_at = now()
                            WHERE id = %s::uuid
                            """,
                            (cleaned, row["id"]),
                        )
                        provenance.record(
                            cur,
                            entity="person",
                            entity_id=row["id"],
                            field="full_name",
                            old=name,
                            new=cleaned,
                            rule_id="cleanup_junk_person_name",
                        )
                    if cleaned:
                        stats["junk_name_sanitized"] += 1
                    else:
                        stats["junk_name_cleared"] += 1

            if date_ci and row["identity_type"] == "cedula":
                stats["date_ci_candidates"] += 1
                if args.apply:
                    # Free the unique (identity_type, identity_number) by moving to unknown.
                    with provenance.source("derived", f"cleanup_date_ci:{row['id']}"):
                        cur.execute(
                            """
                            UPDATE avila.person
                            SET identity_type = 'unknown',
                                identity_number = NULL,
                                provisional_key = coalesce(
                                  provisional_key,
                                  'junk_date:' || %s
                                ),
                                full_name = CASE
                                  WHEN full_name IS NULL OR full_name = %s THEN NULL
                                  ELSE full_name
                                END,
                                updated_at = now()
                            WHERE id = %s::uuid
                            """,
                            (ci, ci, row["id"]),
                        )
                        provenance.record(
                            cur,
                            entity="person",
                            entity_id=row["id"],
                            field="identity_number",
                            old=ci,
                            new=None,
                            rule_id="cleanup_date_like_ci",
                        )
                    stats["date_ci_cleared"] += 1

        if args.apply:
            conn.commit()
        else:
            conn.rollback()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "cleanup-junk-person-names.md"
    lines = [
        "# Cleanup junk person names",
        "",
        f"Mode: {'apply' if args.apply else 'dry-run'}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, n in sorted(stats.items()):
        lines.append(f"| {key} | {n} |")
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    provenance.finish_run(url, dict(stats))
    print(json.dumps({"apply": args.apply, **dict(stats), "report": str(report)}))
    print(f"wrote {report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
