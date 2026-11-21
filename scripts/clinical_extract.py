#!/usr/bin/env python3
"""Read every clinical page into one local record per report. No Neon writes.

  PYTHONPATH=scripts .venv/bin/python scripts/clinical_extract.py
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_extract.py --limit 500
  PYTHONPATH=scripts .venv/bin/python scripts/clinical_extract.py --invoices 12843,7394

Pages of type informe_medico, orden_servicio, laboratorio, and imagenologia are
parsed (clinical_parse.parse_page), consecutive pages of one report are merged,
and each report carries the invoice's persons, the fiscal service lines, and the
especialidad of linked authorization lines so the resolver needs no database.

Stdout and output/runs/clinical-truth.md are counts only.
PHI stays in output/runs/clinical-truth.jsonl (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clinical_parse import (  # noqa: E402
    EXTRACTOR_VERSION,
    REPORT_KINDS,
    group_report_pages,
    parse_page,
    text_fingerprint,
)
from env_load import load_env  # noqa: E402
from especialidad_normalize import best_specialty, normalize_text  # noqa: E402
from ocr_invoice_pages import _read_cache  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_JSONL = ROOT / "output" / "runs" / "clinical-truth.jsonl"
OUT_MD = ROOT / "output" / "runs" / "clinical-truth.md"
FISCAL_JSONL = ROOT / "output" / "invoices" / "fiscal-extract.jsonl"


def load_documents(cur, wanted: set[str] | None) -> list[dict]:
    cur.execute(
        """
        SELECT d.id::text AS document_id, d.source_file_id::text AS source_file_id, d.page_index,
               d.document_type::text AS document_type, d.invoice_id::text AS invoice_id,
               i.invoice_number, sf.backup_path
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        LEFT JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE d.document_type::text = ANY(%s)
        ORDER BY sf.backup_path, d.page_index
        """,
        (list(REPORT_KINDS),),
    )
    rows = cur.fetchall()
    if wanted is not None:
        rows = [row for row in rows if row["invoice_number"] in wanted]
    return rows


def load_invoice_persons(cur) -> dict[str, list[dict]]:
    cur.execute(
        """
        SELECT ip.invoice_id::text AS invoice_id, ip.person_id::text AS person_id, ip.role::text AS role,
               p.full_name, p.identity_number
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        """
    )
    out: dict[str, list[dict]] = defaultdict(list)
    for row in cur.fetchall():
        out[row["invoice_id"]].append(
            {
                "person_id": row["person_id"],
                "role": row["role"],
                "full_name": row["full_name"],
                "identity_number": row["identity_number"],
            }
        )
    return out


def load_auth_specialties(cur) -> dict[str, list[str]]:
    cur.execute(
        """
        SELECT al.invoice_id::text AS invoice_id, e.code
        FROM avila.authorization_line al
        JOIN avila.especialidad e ON e.id = al.especialidad_id
        WHERE al.invoice_id IS NOT NULL
        """
    )
    out: dict[str, list[str]] = defaultdict(list)
    for row in cur.fetchall():
        if row["code"] not in out[row["invoice_id"]]:
            out[row["invoice_id"]].append(row["code"])
    return out


def load_fiscal_terms() -> dict[str, list[dict]]:
    """Especialidad matches from the fiscal service lines, keyed by invoice id."""
    out: dict[str, list[dict]] = {}
    if not FISCAL_JSONL.is_file():
        return out
    for line in FISCAL_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        terms = []
        for service in row.get("services") or []:
            for match in normalize_text(str(service), "fiscal_line"):
                terms.append(
                    {
                        "context": "fiscal_line",
                        "raw": match.raw,
                        "l1": match.l1,
                        "method": match.method,
                        "distance": match.distance,
                        "kind": match.kind,
                        "term": match.term.term if match.term else None,
                        "especialidad": match.especialidad if match.is_specialty else None,
                        "procedimiento": match.procedimiento,
                        "degree": match.degree,
                        "university": match.university,
                    }
                )
        if terms and row.get("invoice_id"):
            out[row["invoice_id"]] = terms
    return out


def _page_text(record: dict | None, page_index: int) -> str:
    pages = (record or {}).get("pages") or []
    idx = int(page_index) - 1
    if 0 <= idx < len(pages):
        return pages[idx].get("text") or ""
    return ""


def build_report(group: list[dict], persons: dict, fiscal: dict, auth: dict) -> dict:
    first = group[0]
    doctors: list[dict] = []
    terms: list[dict] = []
    patient: dict = {"name": None, "ci": None, "edad": None, "rule": None}
    encounter_date = None
    diagnosis = None
    has_title = False
    for page in group:
        parsed = page["parsed"]
        has_title = has_title or parsed["has_title"]
        for doctor in parsed["doctors"]:
            doctors.append(dict(doctor, document_id=page["document_id"], page_index=page["page_index"]))
        for term in parsed["terms"]:
            terms.append(dict(term, document_id=page["document_id"]))
        if not patient["name"] and not patient["ci"]:
            patient = parsed["patient"]
        elif not patient["ci"] and parsed["patient"]["ci"]:
            patient = dict(patient, ci=parsed["patient"]["ci"])
        encounter_date = encounter_date or parsed["encounter_date"]
        diagnosis = diagnosis or parsed["diagnosis"]
    invoice_id = first["invoice_id"]
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "primary_document_id": first["document_id"],
        "document_ids": [page["document_id"] for page in group],
        "document_type": first["document_type"],
        "report_kind": REPORT_KINDS[first["document_type"]],
        "source_ref": f"{first['backup_path']}#{first['page_index']}",
        "invoice_id": invoice_id,
        "invoice_number": first["invoice_number"],
        "has_title": has_title,
        "doctors": doctors,
        "terms": terms,
        "patient": patient,
        "encounter_date": encounter_date,
        "diagnosis": diagnosis,
        "fingerprint": text_fingerprint(" ".join(page["text"] for page in group)),
        "invoice_persons": persons.get(invoice_id, []) if invoice_id else [],
        "fiscal_terms": fiscal.get(invoice_id, []) if invoice_id else [],
        "auth_especialidades": auth.get(invoice_id, []) if invoice_id else [],
    }


def count_report(report: dict, stats: Counter) -> None:
    stats["reports"] += 1
    stats[f"kind:{report['report_kind']}"] += 1
    stats["pages"] += len(report["document_ids"])
    if len(report["document_ids"]) > 1:
        stats["multi_page_reports"] += 1
    if report["doctors"]:
        stats["with_doctor"] += 1
    if any(d["mpps"] for d in report["doctors"]):
        stats["with_mpps"] += 1
    if report["patient"]["name"]:
        stats["with_patient_name"] += 1
    if report["patient"]["ci"]:
        stats["with_patient_ci"] += 1
    if report["diagnosis"]:
        stats["with_diagnosis"] += 1
    if report["encounter_date"]:
        stats["with_date"] += 1
    if any(t["especialidad"] for t in report["terms"]):
        stats["with_page_especialidad"] += 1


def render_md(stats: Counter) -> str:
    lines = [
        "# Clinical truth",
        "",
        "Counts only. Names, cédulas, and diagnoses stay in `clinical-truth.jsonl`.",
        "",
        "| Counter | Value |",
        "| --- | ---: |",
    ]
    for key in sorted(stats):
        lines.append(f"| {key} | {stats[key]} |")
    return "\n".join(lines) + "\n"


def _wanted(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many pages")
    parser.add_argument("--invoices", help="Comma-separated factura numbers")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")

    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        documents = load_documents(cur, _wanted(args.invoices))
        persons = load_invoice_persons(cur)
        auth = load_auth_specialties(cur)
        conn.rollback()
    if args.limit:
        documents = documents[: args.limit]
    fiscal = load_fiscal_terms()

    stats: Counter = Counter()
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, list[dict]] = defaultdict(list)
    for row in documents:
        by_file[row["backup_path"]].append(row)

    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for backup_path, rows in by_file.items():
            record = _read_cache(backup_path)
            if record is None:
                stats["missing_cache_files"] += 1
            pages = []
            for row in rows:
                text = _page_text(record, row["page_index"])
                if not text.strip():
                    stats["empty_pages"] += 1
                pages.append(dict(row, text=text, parsed=parse_page(text)))
            for group in group_report_pages(pages):
                report = build_report(group, persons, fiscal, auth)
                count_report(report, stats)
                out.write(json.dumps(report, ensure_ascii=False) + "\n")
            if stats["reports"] and stats["reports"] % 2000 < len(rows):
                print(f"reports {stats['reports']}", flush=True)

    OUT_MD.write_text(render_md(stats), encoding="utf-8")
    print({key: stats[key] for key in sorted(stats)}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
