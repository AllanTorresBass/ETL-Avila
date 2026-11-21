#!/usr/bin/env python3
"""Coverage cohorts and precision sample for the clinical phase.

  PYTHONPATH=scripts .venv/bin/python scripts/clinical_verify.py                 # counts from decisions + Neon
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_verify.py --apply         # also store clinical_verify_snapshot
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_verify.py --sample 200    # write a review worksheet
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_verify.py --score output/runs/clinical-sample.csv

Cohorts come from Neon once atenciones exist there, otherwise from
output/runs/clinical-decisions.jsonl (the dry-run baseline).

The sample worksheet (git-ignored) lists random non-duplicate atenciones with
the decided médico, especialidad, and patient rule, plus empty columns
doctor_ok, especialidad_ok, patient_ok. Mark each 1 or 0, then --score prints
precision against the plan targets (doctor 95%, especialidad 90%, patient 95%).
Stdout is counts only.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_load import load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "output" / "runs" / "clinical-decisions.jsonl"
SAMPLE_CSV = ROOT / "output" / "runs" / "clinical-sample.csv"
REPORT_MD = ROOT / "output" / "runs" / "clinical-verify.md"
TARGETS = {"doctor_ok": 0.95, "especialidad_ok": 0.90, "patient_ok": 0.95}
UNKNOWN_TERM_TARGET = 0.03
SAMPLE_FIELDS = (
    "primary_document_id",
    "source_ref",
    "report_kind",
    "medico_name",
    "medico_mpps",
    "especialidad",
    "especialidad_source",
    "person_link_rule",
    "person_id",
    "doctor_ok",
    "especialidad_ok",
    "patient_ok",
)


def load_decisions() -> list[dict]:
    if not DECISIONS.is_file():
        return []
    return [json.loads(line) for line in DECISIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


def cohorts_from_decisions(records: list[dict]) -> Counter:
    stats: Counter = Counter()
    observations = Counter()
    for record in records:
        if record["type"] == "medico":
            stats["medicos"] += 1
            stats["medicos_mpps" if record["mpps"] else "medicos_provisional"] += 1
            if record["primary_especialidad"]:
                stats["medicos_with_especialidad"] += 1
        elif record["type"] == "review":
            stats[f"review_open:{record['kind']}"] += 1
        else:
            count_atencion(stats, record["report_kind"], record["link_status"], record["medico_key"],
                           record["especialidad"], record["person_id"], record["especialidad_source"],
                           record["person_link_rule"])
            for term in record["observations"]:
                observations[term["method"]] += 1
    add_observation_rate(stats, observations)
    stats["source:decisions"] = 1
    return stats


def count_atencion(stats: Counter, kind, status, medico, especialidad, person, esp_source, person_rule) -> None:
    stats["atenciones"] += 1
    stats[f"status:{status}"] += 1
    if status == "duplicate":
        return
    stats["atenciones_unique"] += 1
    stats[f"kind:{kind}"] += 1
    stats[f"especialidad_source:{esp_source or 'none'}"] += 1
    stats[f"person_rule:{person_rule or 'none'}"] += 1
    for flag, value in (("with_medico", medico), ("with_especialidad", especialidad), ("with_person", person)):
        if value:
            stats[flag] += 1
            stats[f"{flag}:{kind}"] += 1


def add_observation_rate(stats: Counter, observations: Counter) -> None:
    total = sum(observations.values())
    stats["observations"] = total
    stats["observations_unknown"] = observations["none"]
    stats["unknown_term_rate_bp"] = round(10000 * observations["none"] / total) if total else 0


def cohorts_from_neon(cur) -> Counter:
    stats: Counter = Counter()
    cur.execute(
        """
        SELECT report_kind, link_status, medico_id IS NOT NULL AS m, especialidad_id IS NOT NULL AS e,
               person_id IS NOT NULL AS p, especialidad_source, person_link_rule, count(*)::int AS n
        FROM avila.atencion
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        """
    )
    for row in cur.fetchall():
        for _ in range(row["n"]):
            count_atencion(stats, row["report_kind"], row["link_status"], row["m"], row["e"], row["p"],
                           row["especialidad_source"], row["person_link_rule"])
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE merged_into IS NULL)::int AS medicos,
               count(*) FILTER (WHERE merged_into IS NULL AND mpps IS NOT NULL)::int AS medicos_mpps,
               count(*) FILTER (WHERE merged_into IS NULL AND mpps IS NULL)::int AS medicos_provisional,
               count(*) FILTER (WHERE merged_into IS NOT NULL)::int AS medicos_merged,
               count(*) FILTER (WHERE merged_into IS NULL AND EXISTS (
                 SELECT 1 FROM avila.medico_especialidad me WHERE me.medico_id = m.id AND me.is_primary
               ))::int AS medicos_with_especialidad
        FROM avila.medico m
        """
    )
    stats.update({k: v for k, v in cur.fetchone().items() if v})
    cur.execute("SELECT kind, count(*)::int AS n FROM avila.review_item WHERE status = 'open' GROUP BY kind")
    for row in cur.fetchall():
        if row["kind"] in ("medico_duplicate", "medico_mpps_conflict", "atencion_patient", "especialidad_unknown"):
            stats[f"review_open:{row['kind']}"] = row["n"]
    cur.execute("SELECT match_method, count(*)::int AS n FROM avila.especialidad_observation GROUP BY 1")
    add_observation_rate(stats, Counter({row["match_method"]: row["n"] for row in cur.fetchall()}))
    stats["source:neon"] = 1
    return stats


def clinical_documents(cur) -> int:
    cur.execute(
        """
        SELECT count(*)::int AS n FROM avila.document
        WHERE document_type::text IN ('informe_medico', 'orden_servicio', 'laboratorio', 'imagenologia')
        """
    )
    return cur.fetchone()["n"]


def write_sample(records: list[dict], size: int, seed: int) -> int:
    medicos = {r["key"]: r for r in records if r["type"] == "medico"}
    pool = [r for r in records if r["type"] == "atencion" and r["link_status"] != "duplicate"]
    rng = random.Random(seed)
    picked = rng.sample(pool, min(size, len(pool)))
    SAMPLE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        for record in picked:
            medico = medicos.get(record["medico_key"] or "") or {}
            writer.writerow(
                {
                    "primary_document_id": record["primary_document_id"],
                    "source_ref": record["source_ref"],
                    "report_kind": record["report_kind"],
                    "medico_name": medico.get("full_name") or "",
                    "medico_mpps": medico.get("mpps") or "",
                    "especialidad": record["especialidad"] or "",
                    "especialidad_source": record["especialidad_source"] or "",
                    "person_link_rule": record["person_link_rule"] or "",
                    "person_id": record["person_id"] or "",
                    "doctor_ok": "",
                    "especialidad_ok": "",
                    "patient_ok": "",
                }
            )
    return len(picked)


def score_sample(path: Path) -> dict[str, str]:
    marks: dict[str, list[int]] = {field: [] for field in TARGETS}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for field in TARGETS:
                value = (row.get(field) or "").strip()
                if value in ("0", "1"):
                    marks[field].append(int(value))
    out = {}
    for field, values in marks.items():
        if not values:
            out[field] = "no marks"
            continue
        precision = sum(values) / len(values)
        verdict = "pass" if precision >= TARGETS[field] else "below target"
        out[field] = f"{precision:.1%} of {len(values)} ({verdict}, target {TARGETS[field]:.0%})"
    return out


def render_md(stats: Counter) -> str:
    rate = stats["unknown_term_rate_bp"] / 100
    verdict = "pass" if rate < UNKNOWN_TERM_TARGET * 100 else "above target"
    lines = [
        "# Clinical verify",
        "",
        f"Unknown especialidad terms: {rate:.2f}% ({verdict}, target < {UNKNOWN_TERM_TARGET:.0%}).",
        "",
        "| Counter | Value |",
        "| --- | ---: |",
    ]
    lines += [f"| {key} | {stats[key]} |" for key in sorted(stats)]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="Store the counters in clinical_verify_snapshot")
    parser.add_argument("--sample", type=int, default=0, help="Write a precision worksheet of N atenciones")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--score", type=Path, help="Score a marked worksheet")
    args = parser.parse_args()

    if args.score:
        print(score_sample(args.score), flush=True)
        return 0

    records = load_decisions()
    if args.sample:
        if not records:
            sys.exit("Missing clinical-decisions.jsonl; run medico_resolve.py first")
        written = write_sample(records, args.sample, args.seed)
        print({"sample_rows": written, "file": str(SAMPLE_CSV.relative_to(ROOT))}, flush=True)
        return 0

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*)::int AS n FROM avila.atencion")
        in_neon = cur.fetchone()["n"]
        stats = cohorts_from_neon(cur) if in_neon else cohorts_from_decisions(records)
        stats["clinical_documents"] = clinical_documents(cur)
        if args.apply:
            cur.execute(
                """
                INSERT INTO avila.clinical_verify_snapshot (id, computed_at, counters)
                VALUES (1, now(), %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET computed_at = now(), counters = EXCLUDED.counters
                """,
                (json.dumps(dict(stats)),),
            )
            conn.commit()
        else:
            conn.rollback()
    REPORT_MD.write_text(render_md(stats), encoding="utf-8")
    print({key: stats[key] for key in sorted(stats)}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
