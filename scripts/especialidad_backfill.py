#!/usr/bin/env python3
"""Normalize authorization_line service text into especialidad / procedimiento.

  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_backfill.py
  PYTHONPATH=scripts .venv/bin/python scripts/especialidad_backfill.py --apply

Reads ``service_description`` (which carries the sábana SERVICIO column when the
description is empty), runs the shared normalizer in the ``auth_line`` context,
records one especialidad_observation per term, and sets ``especialidad_id`` /
``procedimiento_id`` with field provenance. Dry-run unless --apply. Counts only.
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
from especialidad_normalize import best_specialty, first_procedure, normalize_text  # noqa: E402
from especialidad_store import load_ids, observation_rows, write_observations  # noqa: E402


def backfill(cur, *, apply: bool) -> None:
    ids = load_ids(cur)
    cur.execute(
        """
        SELECT id::text AS id, service_description,
               especialidad_id::text AS especialidad_id, procedimiento_id::text AS procedimiento_id
        FROM avila.authorization_line
        WHERE service_description IS NOT NULL AND btrim(service_description) <> ''
        """
    )
    lines = cur.fetchall()
    observations: list[tuple] = []
    updates: list[tuple] = []
    for line in lines:
        provenance.counters["lines"] += 1
        matches = normalize_text(line["service_description"], "auth_line")
        observations.extend(observation_rows(matches, f"auth:{line['id']}", ids))
        specialty = best_specialty(matches)
        procedure = first_procedure(matches)
        esp_id = ids.especialidad.get(specialty.especialidad) if specialty else None
        proc_id = ids.procedimiento.get(procedure.procedimiento) if procedure else None
        provenance.counters["with_especialidad" if esp_id else "no_especialidad"] += 1
        if proc_id:
            provenance.counters["with_procedimiento"] += 1
        if (esp_id, proc_id) == (line["especialidad_id"], line["procedimiento_id"]):
            continue
        updates.append((esp_id, proc_id, line["id"]))
        for field, old, new, match in (
            ("especialidad_id", line["especialidad_id"], esp_id, specialty),
            ("procedimiento_id", line["procedimiento_id"], proc_id, procedure),
        ):
            provenance.record(
                cur,
                entity="authorization_line",
                entity_id=line["id"],
                field=field,
                old=old,
                new=new,
                rule_id=f"especialidad_auth_{match.method}" if match else "especialidad_auth_none",
                source_kind="workbook",
                source_ref=f"auth:{line['id']}",
            )
    provenance.counters["lines_changed"] = len(updates)
    if not apply:
        return
    write_observations(cur, observations)
    cur.executemany(
        """
        UPDATE avila.authorization_line
        SET especialidad_id = %s::uuid, procedimiento_id = %s::uuid, updated_at = now()
        WHERE id = %s::uuid
        """,
        updates,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "especialidad_backfill", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        with conn.pipeline():
            backfill(cur, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url)
    print("apply" if args.apply else "dry-run", dict(sorted(provenance.counters.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
