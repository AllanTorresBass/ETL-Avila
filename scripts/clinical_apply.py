#!/usr/bin/env python3
"""Write clinical-decisions.jsonl to Neon: médicos, especialidades, menciones, atenciones.

  PYTHONPATH=scripts .venv/bin/python scripts/clinical_apply.py           # dry-run, rolls back
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_apply.py --apply

Runs every write inside one transaction and rolls back unless --apply, so the
dry-run checks constraints and reports the same counts as a real run.

- medico: upsert on mpps or provisional_key. A doctor seen only by license gets
  the placeholder name "Sin nombre (MPPS n)". Merged médicos stay merged;
  atenciones point at the merge target.
- medico_especialidad: OCR-sourced rows are replaced; review rows are kept.
- medico_mention: upsert on (document_id, role, name_folded).
- atencion: upsert on primary_document_id. A patient, especialidad, or médico
  set by a reviewer (source or rule ``review``) is not overwritten.
- especialidad_observation for every page term; review_item for every decision
  that needs a person.

Every field change records field_provenance. Stdout is counts only.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from especialidad_store import load_ids, observation_rows_from_dicts, write_observations  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IN_JSONL = ROOT / "output" / "runs" / "clinical-decisions.jsonl"
MEDICO_FIELDS = ("title", "full_name", "name_folded", "degree", "degree_university", "colegio_number", "rif")
ATENCION_FIELDS = ("person_id", "medico_id", "especialidad_id", "procedimiento_id", "link_status")


def load_decisions() -> tuple[list[dict], list[dict], list[dict]]:
    if not IN_JSONL.is_file():
        sys.exit(f"Missing {IN_JSONL.relative_to(ROOT)}; run medico_resolve.py first")
    medicos, atenciones, reviews = [], [], []
    for line in IN_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        {"medico": medicos, "atencion": atenciones, "review": reviews}[row["type"]].append(row)
    return medicos, atenciones, reviews


def _placeholder(record: dict) -> tuple[str, str]:
    if record["full_name"] and record["name_folded"]:
        return record["full_name"], record["name_folded"]
    return f"Sin nombre (MPPS {record['mpps']})", f"MPPS {record['mpps']}"


def apply_medicos(cur, medicos: list[dict], ids) -> dict[str, str]:
    """Upsert médicos; return cluster key -> effective medico id (merge target when merged)."""
    cur.execute(
        """
        SELECT id::text AS id, mpps, provisional_key, merged_into::text AS merged_into,
               title, full_name, name_folded, degree, degree_university, colegio_number, rif
        FROM avila.medico
        """
    )
    existing: dict[str, dict] = {}
    for row in cur.fetchall():
        if row["mpps"]:
            existing[f"mpps:{row['mpps']}"] = row
        if row["provisional_key"]:
            existing[row["provisional_key"]] = row

    key_to_id: dict[str, str] = {}
    inserts, updates, especialidad_rows = [], [], []
    processed: set[str] = set()
    for record in medicos:
        full_name, name_folded = _placeholder(record)
        values = {
            "title": record["title"],
            "full_name": full_name,
            "name_folded": name_folded,
            "degree": record["degree"],
            "degree_university": record["degree_university"],
            "colegio_number": record["colegio_number"],
            "rif": record["rif"],
        }
        current = existing.get(record["key"])
        if current is None:
            medico_id = str(uuid.uuid4())
            inserts.append((medico_id, record["mpps"], record["provisional_key"], *values.values()))
            provenance.counters["medico_insert"] += 1
            old = dict.fromkeys(MEDICO_FIELDS)
        else:
            medico_id = current["id"]
            old = {f: current[f] for f in MEDICO_FIELDS}
            if any(old[f] != values[f] for f in MEDICO_FIELDS):
                updates.append((*values.values(), medico_id))
                provenance.counters["medico_update"] += 1
        for field in MEDICO_FIELDS:
            provenance.record(
                cur,
                entity="medico",
                entity_id=medico_id,
                field=field,
                old=old[field],
                new=values[field],
                rule_id="medico_mpps_cluster" if record["mpps"] else "medico_name_cluster",
                source_kind="ocr",
                source_ref=record["key"],
            )
        processed.add(medico_id)
        effective = (current or {}).get("merged_into") or medico_id
        key_to_id[record["key"]] = effective
        for esp in record["especialidades"]:
            esp_id = ids.especialidad.get(esp["code"])
            if esp_id:
                especialidad_rows.append((medico_id, esp_id, esp["source"], esp["evidence_count"], esp["is_primary"]))

    cur.executemany(
        """
        INSERT INTO avila.medico (
          id, mpps, provisional_key, title, full_name, name_folded, degree, degree_university, colegio_number, rif
        ) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        inserts,
    )
    cur.executemany(
        """
        UPDATE avila.medico SET
          title = %s, full_name = %s, name_folded = %s, degree = %s, degree_university = %s,
          colegio_number = %s, rif = %s, updated_at = now()
        WHERE id = %s::uuid
        """,
        updates,
    )
    medico_ids = sorted(processed)
    cur.execute(
        "DELETE FROM avila.medico_especialidad WHERE medico_id = ANY(%s::uuid[]) AND source <> 'review'",
        (medico_ids,),
    )
    cur.executemany(
        """
        INSERT INTO avila.medico_especialidad (medico_id, especialidad_id, source, evidence_count, is_primary)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s)
        ON CONFLICT (medico_id, especialidad_id) DO NOTHING
        """,
        especialidad_rows,
    )
    provenance.counters["medico_especialidad_rows"] = len(especialidad_rows)
    return key_to_id


def apply_atenciones(cur, atenciones: list[dict], key_to_id: dict[str, str], ids) -> dict[str, str]:
    """Upsert atenciones; return primary_document_id -> atencion id."""
    cur.execute(
        """
        SELECT id::text AS id, primary_document_id::text AS primary_document_id,
               person_id::text AS person_id, medico_id::text AS medico_id,
               especialidad_id::text AS especialidad_id, procedimiento_id::text AS procedimiento_id,
               link_status, especialidad_source, person_link_rule
        FROM avila.atencion
        """
    )
    existing = {row["primary_document_id"]: row for row in cur.fetchall()}
    doc_to_id: dict[str, str] = {}
    rows, mentions, observations = [], [], []
    for record in atenciones:
        doc = record["primary_document_id"]
        current = existing.get(doc)
        atencion_id = current["id"] if current else str(uuid.uuid4())
        doc_to_id[doc] = atencion_id
        values = {
            "person_id": record["person_id"],
            "medico_id": key_to_id.get(record["medico_key"]) if record["medico_key"] else None,
            "especialidad_id": ids.especialidad.get(record["especialidad"]) if record["especialidad"] else None,
            "procedimiento_id": ids.procedimiento.get(record["procedimiento"]) if record["procedimiento"] else None,
            "link_status": record["link_status"],
        }
        person_rule = record["person_link_rule"]
        especialidad_source = record["especialidad_source"]
        if current and current["person_link_rule"] == "review" and current["person_id"]:
            values["person_id"], person_rule = current["person_id"], "review"
            if values["link_status"] == "review":
                values["link_status"] = "partial"
            provenance.counters["kept_reviewed_person"] += 1
        if current and current["especialidad_source"] == "review":
            values["especialidad_id"], especialidad_source = current["especialidad_id"], "review"
            provenance.counters["kept_reviewed_especialidad"] += 1
        duplicate_of = doc_to_id.get(record["duplicate_of_document"]) if record["duplicate_of_document"] else None
        old = {f: current[f] for f in ATENCION_FIELDS} if current else dict.fromkeys(ATENCION_FIELDS)
        provenance.counters["atencion_insert" if not current else "atencion_seen"] += 1
        for field in ATENCION_FIELDS:
            provenance.record(
                cur,
                entity="atencion",
                entity_id=atencion_id,
                field=field,
                old=old[field],
                new=values[field],
                rule_id=_rule(field, person_rule, especialidad_source),
                source_kind="ocr",
                source_ref=record["source_ref"],
                confidence=record["confidence"],
            )
        rows.append(
            (
                atencion_id,
                doc,
                record["document_ids"],
                record["invoice_id"],
                values["person_id"],
                values["medico_id"],
                values["especialidad_id"],
                values["procedimiento_id"],
                ids.especialidad.get(record["referred_especialidad"]) if record["referred_especialidad"] else None,
                especialidad_source,
                person_rule,
                record["encounter_date"],
                record["diagnosis_text"],
                record["report_kind"],
                values["link_status"],
                duplicate_of,
                record["confidence"],
                record["extractor_version"],
                record["text_fingerprint"],
            )
        )
        for mention in record["mentions"]:
            mentions.append(
                (
                    mention["document_id"],
                    key_to_id.get(mention["medico_key"]),
                    mention["role"],
                    mention["zone"],
                    mention["mpps_raw_hash"],
                    mention["name_folded"][:160],
                    mention["confidence"],
                    mention["rule_id"],
                    provenance.current_run_id(),
                )
            )
        observations.extend(observation_rows_from_dicts(record["observations"], f"doc:{doc}", ids))

    cur.executemany(
        """
        INSERT INTO avila.atencion (
          id, primary_document_id, document_ids, invoice_id, person_id, medico_id, especialidad_id,
          procedimiento_id, referred_especialidad_id, especialidad_source, person_link_rule, encounter_date,
          diagnosis_text, report_kind, link_status, duplicate_of, confidence, extractor_version, text_fingerprint
        ) VALUES (
          %s::uuid, %s::uuid, %s::uuid[], %s::uuid, %s::uuid, %s::uuid, %s::uuid,
          %s::uuid, %s::uuid, %s, %s, %s::date,
          %s, %s, %s, %s::uuid, %s, %s, %s
        )
        ON CONFLICT (primary_document_id) DO UPDATE SET
          document_ids = EXCLUDED.document_ids,
          invoice_id = EXCLUDED.invoice_id,
          person_id = EXCLUDED.person_id,
          medico_id = EXCLUDED.medico_id,
          especialidad_id = EXCLUDED.especialidad_id,
          procedimiento_id = EXCLUDED.procedimiento_id,
          referred_especialidad_id = EXCLUDED.referred_especialidad_id,
          especialidad_source = EXCLUDED.especialidad_source,
          person_link_rule = EXCLUDED.person_link_rule,
          encounter_date = EXCLUDED.encounter_date,
          diagnosis_text = EXCLUDED.diagnosis_text,
          report_kind = EXCLUDED.report_kind,
          link_status = EXCLUDED.link_status,
          duplicate_of = EXCLUDED.duplicate_of,
          confidence = EXCLUDED.confidence,
          extractor_version = EXCLUDED.extractor_version,
          text_fingerprint = EXCLUDED.text_fingerprint,
          updated_at = now()
        """,
        rows,
    )
    cur.executemany(
        """
        INSERT INTO avila.medico_mention (
          document_id, medico_id, role, zone, mpps_raw_hash, name_folded, confidence, rule_id, run_id
        ) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::uuid)
        ON CONFLICT (document_id, role, name_folded) DO UPDATE SET
          medico_id = EXCLUDED.medico_id,
          zone = EXCLUDED.zone,
          mpps_raw_hash = EXCLUDED.mpps_raw_hash,
          confidence = EXCLUDED.confidence,
          rule_id = EXCLUDED.rule_id,
          run_id = EXCLUDED.run_id
        """,
        mentions,
    )
    write_observations(cur, observations)
    provenance.counters["mentions"] = len(mentions)
    provenance.counters["observations"] = len(observations)
    return doc_to_id


def _rule(field: str, person_rule: str | None, especialidad_source: str | None) -> str:
    if field == "person_id":
        return f"atencion_person_{person_rule or 'none'}"
    if field == "especialidad_id":
        return f"atencion_especialidad_{especialidad_source or 'none'}"
    return f"atencion_{field}"


def apply_reviews(cur, reviews: list[dict], key_to_id: dict[str, str], doc_to_id: dict[str, str]) -> None:
    for review in reviews:
        doc = review.get("primary_document_id")
        provenance.open_review(
            cur,
            kind=review["kind"],
            dedupe_key=review["dedupe_key"],
            person_id=review.get("person_id"),
            invoice_id=review.get("invoice_id"),
            document_id=doc,
            medico_id=key_to_id.get(review["medico_key"]) if review.get("medico_key") else None,
            other_medico_id=key_to_id.get(review["other_medico_key"]) if review.get("other_medico_key") else None,
            atencion_id=doc_to_id.get(doc) if doc else None,
            evidence=review["evidence"],
            score=review.get("score"),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    medicos, atenciones, reviews = load_decisions()
    provenance.start_run(url, "clinical_apply", vars(args), apply=args.apply)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        ids = load_ids(cur)
        with conn.pipeline():
            key_to_id = apply_medicos(cur, medicos, ids)
        with conn.pipeline():
            doc_to_id = apply_atenciones(cur, atenciones, key_to_id, ids)
        with conn.pipeline():
            apply_reviews(cur, reviews, key_to_id, doc_to_id)
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
