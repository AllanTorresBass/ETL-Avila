#!/usr/bin/env python3
"""Load the especialidad catalog into Neon, or mine the unknown-term backlog.

  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_catalog.py load
  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_catalog.py load --apply
  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_catalog.py mine
  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_catalog.py mine --apply

``load`` upserts areas, especialidades (parents before children), procedimientos,
and terms from scripts/data/*.csv. Terms added through review are never
overwritten. ``mine`` writes output/runs/especialidad-unknown.csv (term, count,
contexts) and, with --apply, opens an ``especialidad_unknown`` review for every
unmatched term seen at least ``--min-count`` times. Dry-run unless --apply.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from especialidad_normalize import Catalog, load_catalog  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNKNOWN_CSV = ROOT / "output" / "runs" / "especialidad-unknown.csv"


def _upsert_areas(cur, catalog: Catalog) -> None:
    for row in catalog.areas.values():
        cur.execute(
            """
            INSERT INTO avila.especialidad_area (code, name_es, sort_order)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name_es = EXCLUDED.name_es, sort_order = EXCLUDED.sort_order
            WHERE (avila.especialidad_area.name_es, avila.especialidad_area.sort_order)
              IS DISTINCT FROM (EXCLUDED.name_es, EXCLUDED.sort_order)
            RETURNING code
            """,
            (row["code"], row["name_es"], int(row["sort_order"] or 0)),
        )
        if cur.fetchone():
            provenance.counters["areas_written"] += 1


def _especialidad_ids(cur) -> dict[str, str]:
    cur.execute("SELECT code, id::text AS id FROM avila.especialidad")
    return {row["code"]: row["id"] for row in cur.fetchall()}


def _upsert_especialidades(cur, catalog: Catalog) -> None:
    rows = sorted(catalog.especialidades.values(), key=lambda row: int(row["level"]))
    ids = _especialidad_ids(cur)
    for row in rows:
        parent_id = ids.get(row["parent_code"]) if row["parent_code"] else None
        values = (
            row["name_es"],
            row["name_practitioner_m"] or None,
            row["name_practitioner_f"] or None,
            row["area"],
            parent_id,
            int(row["level"]),
            row["marketing_category"] or None,
        )
        cur.execute(
            """
            SELECT name_es, name_practitioner_m, name_practitioner_f, area_code,
                   parent_id::text AS parent_id, level, marketing_category
            FROM avila.especialidad WHERE code = %s
            """,
            (row["code"],),
        )
        before = cur.fetchone()
        old = tuple(before.values()) if before else None
        if old == values:
            continue
        cur.execute(
            """
            INSERT INTO avila.especialidad (
              code, name_es, name_practitioner_m, name_practitioner_f,
              area_code, parent_id, level, marketing_category
            ) VALUES (%s, %s, %s, %s, %s, %s::uuid, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
              name_es = EXCLUDED.name_es,
              name_practitioner_m = EXCLUDED.name_practitioner_m,
              name_practitioner_f = EXCLUDED.name_practitioner_f,
              area_code = EXCLUDED.area_code,
              parent_id = EXCLUDED.parent_id,
              level = EXCLUDED.level,
              marketing_category = EXCLUDED.marketing_category,
              updated_at = now()
            RETURNING id::text AS id
            """,
            (row["code"], *values),
        )
        new_id = cur.fetchone()["id"]
        ids[row["code"]] = new_id
        provenance.record(
            cur,
            entity="especialidad",
            entity_id=new_id,
            field="definition",
            old=repr(old) if old else None,
            new=repr(values),
            rule_id="especialidad_catalog_seed",
            source_kind="manual",
            source_ref="scripts/data/especialidades.csv",
        )
        provenance.counters["especialidades_written"] += 1


def _upsert_procedimientos(cur, catalog: Catalog) -> dict[str, str]:
    ids = _especialidad_ids(cur)
    for row in catalog.procedimientos.values():
        cur.execute(
            """
            INSERT INTO avila.procedimiento (code, name_es, especialidad_id, modality)
            VALUES (%s, %s, %s::uuid, %s)
            ON CONFLICT (code) DO UPDATE SET
              name_es = EXCLUDED.name_es,
              especialidad_id = EXCLUDED.especialidad_id,
              modality = EXCLUDED.modality
            WHERE (avila.procedimiento.name_es, avila.procedimiento.especialidad_id, avila.procedimiento.modality)
              IS DISTINCT FROM (EXCLUDED.name_es, EXCLUDED.especialidad_id, EXCLUDED.modality)
            RETURNING id
            """,
            (row["code"], row["name_es"], ids.get(row["especialidad_code"]), row["modality"]),
        )
        if cur.fetchone():
            provenance.counters["procedimientos_written"] += 1
    cur.execute("SELECT code, id::text AS id FROM avila.procedimiento")
    return {row["code"]: row["id"] for row in cur.fetchall()}


def _upsert_terms(cur, catalog: Catalog, proc_ids: dict[str, str]) -> None:
    esp_ids = _especialidad_ids(cur)
    cur.execute(
        """
        SELECT term_folded, id::text AS id, kind, especialidad_id::text AS esp,
               procedimiento_id::text AS proc, degree_code, source
        FROM avila.especialidad_term
        """
    )
    existing = {row["term_folded"]: row for row in cur.fetchall()}
    terms = list(catalog.single.values()) + list(catalog.phrases.values())
    for term in terms:
        esp_id = esp_ids.get(term.especialidad) if term.especialidad else None
        proc_id = proc_ids.get(term.procedimiento) if term.procedimiento else None
        before = existing.get(term.term)
        if before and before["source"] == "review":
            provenance.counters["terms_kept_review"] += 1
            continue
        new = (term.kind, esp_id, proc_id, term.degree)
        old = (before["kind"], before["esp"], before["proc"], before["degree_code"]) if before else None
        if old == new:
            continue
        cur.execute(
            """
            INSERT INTO avila.especialidad_term (term_folded, kind, especialidad_id, procedimiento_id, degree_code, source)
            VALUES (%s, %s, %s::uuid, %s::uuid, %s, 'seed')
            ON CONFLICT (term_folded) DO UPDATE SET
              kind = EXCLUDED.kind,
              especialidad_id = EXCLUDED.especialidad_id,
              procedimiento_id = EXCLUDED.procedimiento_id,
              degree_code = EXCLUDED.degree_code
            RETURNING id::text AS id
            """,
            (term.term, *new),
        )
        term_id = cur.fetchone()["id"]
        provenance.record(
            cur,
            entity="especialidad_term",
            entity_id=term_id,
            field="target",
            old=repr(old) if old else None,
            new=repr(new),
            rule_id="especialidad_term_seed",
            source_kind="manual",
            source_ref="scripts/data/especialidad_terms.csv",
        )
        provenance.counters["terms_written"] += 1


def load(cur) -> None:
    catalog = load_catalog()
    _upsert_areas(cur, catalog)
    _upsert_especialidades(cur, catalog)
    proc_ids = _upsert_procedimientos(cur, catalog)
    _upsert_terms(cur, catalog, proc_ids)
    provenance.counters["catalog_especialidades"] = len(catalog.especialidades)
    provenance.counters["catalog_terms"] = len(catalog.single) + len(catalog.phrases)


def mine(cur, *, min_count: int, apply: bool) -> None:
    catalog = load_catalog()
    known = set(catalog.single) | {" ".join(key) for key in catalog.phrases}
    cur.execute(
        """
        SELECT l1_term, count(*)::int AS n, array_agg(DISTINCT context) AS contexts
        FROM avila.especialidad_observation
        WHERE match_method = 'none'
        GROUP BY l1_term
        ORDER BY n DESC, l1_term
        """
    )
    rows = [row for row in cur.fetchall() if row["l1_term"] not in known]
    cur.execute("SELECT count(*)::int AS n FROM avila.especialidad_observation")
    total = cur.fetchone()["n"]
    unmatched = sum(row["n"] for row in rows)
    UNKNOWN_CSV.parent.mkdir(parents=True, exist_ok=True)
    with UNKNOWN_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["term", "count", "contexts"])
        for row in rows:
            writer.writerow([row["l1_term"], row["n"], "|".join(sorted(row["contexts"]))])
    provenance.counters["observations"] = total
    provenance.counters["unknown_terms"] = len(rows)
    provenance.counters["unknown_observations"] = unmatched
    provenance.counters["unknown_share_bp"] = round(unmatched * 10000 / total) if total else 0
    for row in rows:
        if row["n"] < min_count:
            continue
        provenance.counters["frequent_unknown"] += 1
        if apply:
            provenance.open_review(
                cur,
                kind="especialidad_unknown",
                dedupe_key=f"especialidad_unknown:{row['l1_term']}",
                evidence={"term": row["l1_term"], "count": row["n"], "contexts": sorted(row["contexts"])},
                score=row["n"],
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("load", "mine"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--min-count", type=int, default=20)
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")

    provenance.start_run(url, f"especialidad_catalog_{args.command}", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        if args.command == "load":
            load(cur)
        else:
            mine(cur, min_count=args.min_count, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url)
    print("apply" if args.apply else "dry-run", dict(sorted(provenance.counters.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
