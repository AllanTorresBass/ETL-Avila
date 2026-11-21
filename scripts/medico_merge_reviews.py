#!/usr/bin/env python3
"""Accept the safe ``medico_duplicate`` reviews by merging the two médicos.

  PYTHONPATH=scripts .venv/bin/python scripts/medico_merge_reviews.py           # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/medico_merge_reviews.py --apply

A pair is safe when the folded names are equal, or when one name's tokens are
inside the other's and the two MPPS differ by at most two digits (or one MPPS
contains the other). Other pairs stay open until a person checks them and
passes their review ids with ``--review-ids``.

Pairs are grouped (A=B and B=C merge into one médico). The survivor is the
médico with the most mentions, then the 5-6 digit MPPS, then the smaller key.
The same effects as accepting in /revision: especialidades, atenciones, and
mentions move to the survivor; the alias keeps its row with ``merged_into``.
The survivor's primary especialidad is recomputed. Each accepted review is
closed with ``resolved_by = etl:medico_merge_reviews``. Stdout is counts only.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from especialidad_normalize import osa_distance  # noqa: E402
from medico_resolve import primary_especialidad  # noqa: E402

RESOLVER = "etl:medico_merge_reviews"


def safe_pair(a_name: str, b_name: str, a_mpps: str | None, b_mpps: str | None) -> bool:
    if a_name == b_name:
        return True
    a_tokens, b_tokens = set(a_name.split()), set(b_name.split())
    if not (a_tokens <= b_tokens or b_tokens <= a_tokens):
        return False
    if not a_mpps or not b_mpps:
        return False
    if a_mpps in b_mpps or b_mpps in a_mpps:
        return True
    return len(a_mpps) == len(b_mpps) and osa_distance(a_mpps, b_mpps, 3) <= 2


class Groups:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def survivor_rank(medico: dict) -> tuple:
    mpps = medico["mpps"] or ""
    return (-medico["mentions"], 0 if 5 <= len(mpps) <= 6 else 1, medico["id"])


def run(cur, *, checked_ids: frozenset[str] = frozenset()) -> None:
    cur.execute(
        """
        SELECT r.id::text AS review_id, r.medico_id::text AS a, r.other_medico_id::text AS b
        FROM avila.review_item r
        WHERE r.kind = 'medico_duplicate' AND r.status = 'open'
          AND r.medico_id IS NOT NULL AND r.other_medico_id IS NOT NULL
        """
    )
    reviews = cur.fetchall()
    cur.execute(
        """
        SELECT m.id::text AS id, m.mpps, m.name_folded, m.merged_into::text AS merged_into,
               (SELECT count(*) FROM avila.medico_mention x WHERE x.medico_id = m.id)::int AS mentions
        FROM avila.medico m
        """
    )
    medicos = {row["id"]: row for row in cur.fetchall()}

    groups = Groups()
    accepted, held = [], []
    for review in reviews:
        a, b = medicos[review["a"]], medicos[review["b"]]
        if a["merged_into"] or b["merged_into"]:
            provenance.counters["skip_already_merged"] += 1
            continue
        checked = review["review_id"][:8] in checked_ids
        if checked or safe_pair(a["name_folded"], b["name_folded"], a["mpps"], b["mpps"]):
            groups.union(a["id"], b["id"])
            accepted.append(review)
        else:
            held.append(review)
    provenance.counters["reviews_accepted"] = len(accepted)
    provenance.counters["reviews_held"] = len(held)

    members: dict[str, list[str]] = defaultdict(list)
    for medico_id in list(groups.parent):
        members[groups.find(medico_id)].append(medico_id)
    survivor_of: dict[str, str] = {}
    for ids in members.values():
        survivor = min((medicos[i] for i in ids), key=survivor_rank)["id"]
        for medico_id in ids:
            if medico_id != survivor:
                survivor_of[medico_id] = survivor
    provenance.counters["groups"] = len(members)
    provenance.counters["medicos_merged"] = len(survivor_of)

    for alias, survivor in survivor_of.items():
        cur.execute(
            """
            INSERT INTO avila.medico_especialidad (medico_id, especialidad_id, source, evidence_count, is_primary)
            SELECT %s::uuid, especialidad_id, source, evidence_count, false
            FROM avila.medico_especialidad WHERE medico_id = %s::uuid
            ON CONFLICT (medico_id, especialidad_id) DO UPDATE SET
              evidence_count = avila.medico_especialidad.evidence_count + EXCLUDED.evidence_count,
              updated_at = now()
            """,
            (survivor, alias),
        )
        cur.execute(
            "UPDATE avila.atencion SET medico_id = %s::uuid, updated_at = now() WHERE medico_id = %s::uuid",
            (survivor, alias),
        )
        provenance.counters["atenciones_moved"] += cur.rowcount
        cur.execute(
            "UPDATE avila.medico_mention SET medico_id = %s::uuid WHERE medico_id = %s::uuid",
            (survivor, alias),
        )
        cur.execute(
            "UPDATE avila.medico SET merged_into = %s::uuid, updated_at = now() WHERE id = %s::uuid OR merged_into = %s::uuid",
            (survivor, alias, alias),
        )
        for entity_id, field, new in ((survivor, "merged_from", alias), (alias, "merged_into", survivor)):
            provenance.record(
                cur,
                entity="medico",
                entity_id=entity_id,
                field=field,
                old=None,
                new=new,
                rule_id="medico_merge_safe_duplicate",
                source_kind="review",
                source_ref="medico_duplicate",
            )
        cur.execute(
            "UPDATE avila.review_item SET medico_id = %s::uuid, updated_at = now() "
            "WHERE medico_id = %s::uuid AND status = 'open'",
            (survivor, alias),
        )
        cur.execute(
            "UPDATE avila.review_item SET other_medico_id = %s::uuid, updated_at = now() "
            "WHERE other_medico_id = %s::uuid AND status = 'open'",
            (survivor, alias),
        )

    for survivor in set(survivor_of.values()):
        cur.execute(
            """
            SELECT e.code, me.evidence_count
            FROM avila.medico_especialidad me JOIN avila.especialidad e ON e.id = me.especialidad_id
            WHERE me.medico_id = %s::uuid
            """,
            (survivor,),
        )
        counts = Counter({row["code"]: row["evidence_count"] for row in cur.fetchall()})
        primary = primary_especialidad(counts)
        cur.execute(
            """
            UPDATE avila.medico_especialidad me SET is_primary = (e.code = %s), updated_at = now()
            FROM avila.especialidad e
            WHERE e.id = me.especialidad_id AND me.medico_id = %s::uuid
            """,
            (primary, survivor),
        )

    accepted_ids = [r["review_id"] for r in accepted]
    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE id = ANY(%s::uuid[]) AND status = 'open'
        """,
        (RESOLVER, accepted_ids),
    )
    cur.execute(
        """
        UPDATE avila.review_item SET status = 'accepted', resolved_by = %s, resolved_at = now(), updated_at = now()
        WHERE kind = 'medico_duplicate' AND status = 'open' AND medico_id = other_medico_id
        """,
        (RESOLVER,),
    )
    provenance.counters["held_pairs_now_same_medico"] = cur.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--review-ids",
        default="",
        help="Comma-separated review id prefixes (8 chars) a person checked and accepts as the same médico",
    )
    args = parser.parse_args()
    checked_ids = frozenset(part.strip()[:8] for part in args.review_ids.split(",") if part.strip())
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "medico_merge_reviews", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        run(cur, checked_ids=checked_ids)
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
