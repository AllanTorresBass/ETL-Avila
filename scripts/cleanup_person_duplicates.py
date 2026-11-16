#!/usr/bin/env python3
"""Clean junk and duplicate provisional rows in avila.person.

Default is --dry-run. Pass --apply to write.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import _NOISE_TOKENS  # noqa: E402
from env_load import load_env  # noqa: E402
from invoice_rules import fold  # noqa: E402
from person_upsert import absorb_provisional, provisional_key_for_name  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

_JUNK_PREFIXES = {
    "FACTURAS",
    "FACTURA",
    "CASOS",
    "RELACION",
    "CINTILLO",
    "SABANA",
    "SABANAS",
    "FORMATO",
}


def is_junk_name(full_name: str | None) -> bool:
    if not full_name or not str(full_name).strip():
        return True
    cleaned = re.sub(r"[,.;:/]+", " ", str(full_name))
    raw_tokens = [fold(t) for t in cleaned.split() if t.strip()]
    tokens = [re.sub(r"[^A-Z0-9]", "", t) for t in raw_tokens]
    tokens = [t for t in tokens if t]
    if not tokens:
        return True
    if tokens[0] in _JUNK_PREFIXES:
        return True
    return all(t in _NOISE_TOKENS or t.isdigit() for t in tokens)


def connect():
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL_UNPOOLED missing")
    return psycopg.connect(url, row_factory=dict_row)


def step_a_junk(cur, *, apply: bool, stats: Counter) -> list[str]:
    cur.execute(
        """
        SELECT id, full_name FROM avila.person
        WHERE identity_number IS NULL
          AND provisional_key IS NOT NULL
        """
    )
    deleted: list[str] = []
    for row in cur.fetchall():
        if not is_junk_name(row["full_name"]):
            continue
        stats["junk_candidates"] += 1
        deleted.append(str(row["id"]))
        if apply:
            # Detach refs then delete
            cur.execute("DELETE FROM avila.invoice_person WHERE person_id = %s", (row["id"],))
            cur.execute(
                "UPDATE avila.document SET person_id = NULL WHERE person_id = %s",
                (row["id"],),
            )
            cur.execute(
                "UPDATE avila.authorization_line SET person_id = NULL WHERE person_id = %s",
                (row["id"],),
            )
            cur.execute("DELETE FROM avila.person WHERE id = %s", (row["id"],))
            stats["junk_deleted"] += 1
    return deleted


def step_b_orphans(cur, *, apply: bool, stats: Counter) -> None:
    cur.execute(
        """
        SELECT p.id
        FROM avila.person p
        WHERE p.provisional_key IS NOT NULL
          AND p.identity_number IS NULL
          AND NOT EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id)
          AND NOT EXISTS (SELECT 1 FROM avila.document d WHERE d.person_id = p.id)
          AND NOT EXISTS (SELECT 1 FROM avila.authorization_line a WHERE a.person_id = p.id)
        """
    )
    for row in cur.fetchall():
        stats["orphan_candidates"] += 1
        if apply:
            cur.execute("DELETE FROM avila.person WHERE id = %s", (row["id"],))
            stats["orphan_deleted"] += 1


def step_c_merge_provisionals(cur, *, apply: bool, stats: Counter) -> None:
    cur.execute(
        """
        SELECT lower(full_name) AS name_key, array_agg(id::text ORDER BY created_at) AS ids
        FROM avila.person
        WHERE identity_number IS NULL
          AND full_name IS NOT NULL
          AND full_name <> ''
        GROUP BY 1
        HAVING count(*) > 1
        """
    )
    for group in cur.fetchall():
        ids = group["ids"]
        stats["provisional_groups"] += 1
        # Survivor: most invoice_person links, then oldest
        best_id = None
        best_score = -1
        for pid in ids:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM avila.invoice_person WHERE person_id = %s::uuid)
                  + (SELECT count(*) FROM avila.document WHERE person_id = %s::uuid)
                  + (SELECT count(*) FROM avila.authorization_line WHERE person_id = %s::uuid)
                  AS score
                """,
                (pid, pid, pid),
            )
            score = cur.fetchone()["score"]
            if score > best_score:
                best_score = score
                best_id = pid
        if not best_id:
            best_id = ids[0]
        cur.execute("SELECT full_name FROM avila.person WHERE id = %s::uuid", (best_id,))
        full_name = cur.fetchone()["full_name"]
        if apply:
            # Normalize survivor key to name-scoped
            cur.execute(
                """
                UPDATE avila.person
                SET provisional_key = %s, updated_at = now()
                WHERE id = %s::uuid
                """,
                (provisional_key_for_name(full_name), best_id),
            )
            absorbed = absorb_provisional(cur, best_id, full_name)
            stats["provisional_absorbed"] += absorbed
        else:
            stats["provisional_would_absorb"] += len(ids) - 1


def step_d_ci_absorb(cur, *, apply: bool, stats: Counter) -> None:
    cur.execute(
        """
        SELECT id, full_name FROM avila.person
        WHERE identity_number IS NOT NULL
          AND full_name IS NOT NULL
          AND full_name <> ''
        """
    )
    for row in cur.fetchall():
        if apply:
            n = absorb_provisional(cur, str(row["id"]), row["full_name"])
            stats["ci_absorbed"] += n
        else:
            cur.execute(
                """
                SELECT count(*)::int AS n FROM avila.person
                WHERE id <> %s
                  AND identity_number IS NULL
                  AND provisional_key IS NOT NULL
                  AND lower(full_name) = lower(%s)
                """,
                (row["id"], row["full_name"]),
            )
            stats["ci_would_absorb"] += cur.fetchone()["n"]


def remaining_dupes(cur) -> dict:
    cur.execute(
        """
        SELECT count(*)::int AS persons,
          count(*) FILTER (WHERE identity_number IS NULL)::int AS without_ci,
          count(*) FILTER (
            WHERE identity_number IS NULL
              AND provisional_key IS NOT NULL
          )::int AS provisional
        FROM avila.person
        """
    )
    overview = cur.fetchone()
    cur.execute(
        """
        SELECT count(*)::int AS groups FROM (
          SELECT lower(full_name)
          FROM avila.person
          WHERE identity_number IS NULL AND full_name IS NOT NULL AND full_name <> ''
          GROUP BY 1 HAVING count(*) > 1
        ) t
        """
    )
    overview = dict(overview)
    overview["duplicate_name_groups"] = cur.fetchone()["groups"]
    cur.execute(
        """
        SELECT count(*)::int AS n FROM avila.person
        WHERE identity_number IS NULL
          AND provisional_key IS NOT NULL
          AND full_name IS NOT NULL
        """
    )
    junk_left = 0
    cur.execute(
        "SELECT full_name FROM avila.person WHERE identity_number IS NULL AND provisional_key IS NOT NULL"
    )
    for row in cur.fetchall():
        if is_junk_name(row["full_name"]):
            junk_left += 1
    overview["junk_name_left"] = junk_left
    return overview


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean duplicate/junk avila.person rows")
    parser.add_argument("--apply", action="store_true", help="Write changes (default dry-run)")
    parser.add_argument(
        "--report",
        default=str(ROOT / "output" / "invoices" / "person-cleanup-report.md"),
    )
    args = parser.parse_args()
    apply = args.apply
    stats: Counter = Counter()

    conn = connect()
    try:
        with conn.cursor() as cur:
            before = remaining_dupes(cur)
            step_a_junk(cur, apply=apply, stats=stats)
            step_b_orphans(cur, apply=apply, stats=stats)
            step_c_merge_provisionals(cur, apply=apply, stats=stats)
            step_d_ci_absorb(cur, apply=apply, stats=stats)
            if apply:
                conn.commit()
            else:
                conn.rollback()
            # Reconnect-ish: after rollback dry-run, before stats still valid;
            # after apply, recompute.
            after = remaining_dupes(cur) if apply else before
            if apply:
                after = remaining_dupes(cur)
    finally:
        conn.close()

    # Fresh after stats when dry-run: estimate from counters
    report = {
        "mode": "apply" if apply else "dry-run",
        "before": before,
        "stats": dict(stats),
        "after": after if apply else {
            "note": "dry-run; after ≈ before minus candidates",
            "junk_candidates": stats["junk_candidates"],
            "orphan_candidates": stats["orphan_candidates"],
            "provisional_would_absorb": stats["provisional_would_absorb"],
            "ci_would_absorb": stats["ci_would_absorb"],
        },
    }

    md_path = Path(args.report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md = [
        "# Person cleanup report",
        "",
        f"Mode: **{report['mode']}**",
        "",
        "## Before",
        "",
        "```json",
        json.dumps(before, indent=2),
        "```",
        "",
        "## Stats",
        "",
        "```json",
        json.dumps(dict(stats), indent=2),
        "```",
        "",
        "## After",
        "",
        "```json",
        json.dumps(report["after"], indent=2),
        "```",
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    json_path = md_path.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
