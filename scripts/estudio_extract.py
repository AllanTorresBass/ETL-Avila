#!/usr/bin/env python3
"""Read fiscal lines, result sheets, and study orders into avila.invoice_service.

  PYTHONPATH=scripts .venv/bin/python scripts/estudio_extract.py
  PYTHONPATH=scripts .venv/bin/python scripts/estudio_extract.py --apply

Dry-run prints counts and rolls back. ``--apply`` replaces the derived rows.
A consult note that only requests a test is not stored. Page text stays in the
OCR cache. ``service_label`` is the most specific study name on that line or
page title: the test, the modality plus the body site, or the procedure.

Requires ``sql/016_estudio.sql``. After the service lines are written, apply
calls ``avila.rebuild_estudios`` so each study is saved under its type, with
every documentation page and result image attached.

The apply is refused when the estudio invoice count is below the neighborhood
in output/runs/medical-tests.md, or when a known consult-only factura gains
an estudio.
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

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from especialidad_normalize import default_catalog, normalize_text  # noqa: E402
from especialidad_store import load_ids, observation_rows, write_observations  # noqa: E402
from estudio_catalogo import assign_catalog  # noqa: E402
from estudio_kind import (  # noqa: E402
    classify_line,
    classify_order,
    classify_result_page,
    family_of,
    specific_name,
)
from fiscal_extract import extract  # noqa: E402
from ocr_invoice_pages import cache_path  # noqa: E402

TYPES = (
    "factura_fiscal",
    "laboratorio",
    "imagenologia",
    "informe_medico",
    "orden_servicio",
    "otro_anexo",
)
# Neighborhood from the read-only scan. Below this, the catalog is still short.
MIN_ESTUDIO_INVOICES = 3200
# Clear patients: one beneficiario (2268) plus self-titular (1249). A drop means
# those invoices fell into the unresolved cohorts.
MIN_LINKED_INVOICES = 3200
CONSULT_ONLY = ("9379", "17345", "18092", "18215", "18252", "18910", "19619", "23803")

PAGE_SQL = """
SELECT d.id::text AS document_id,
       d.invoice_id::text AS invoice_id,
       coalesce(i.invoice_number, '') AS invoice_number,
       d.page_index,
       d.document_type::text AS document_type,
       sf.backup_path
FROM avila.document d
JOIN avila.source_file sf ON sf.id = d.source_file_id
LEFT JOIN avila.invoice i ON i.id = d.invoice_id
WHERE d.document_type::text = ANY(%s)
  AND d.invoice_id IS NOT NULL
"""

PERSON_SQL = """
SELECT invoice_id::text AS invoice_id,
       person_id::text AS person_id,
       role
FROM avila.invoice_person
WHERE role IN ('beneficiario', 'titular')
"""


def _page_text(data: dict, page_index: int) -> str:
    pages = data.get("pages") or []
    for page in pages:
        if page.get("page") == page_index:
            return page.get("text") or ""
    if page_index == 1 and len(pages) == 1:
        return pages[0].get("text") or ""
    return ""


def resolve_patient(beneficiarios: list[str], titulares: list[str]) -> tuple[str | None, str]:
    """One patient per factura. The sole beneficiario wins; otherwise the sole titular."""
    patients = list(dict.fromkeys(beneficiarios))
    holders = list(dict.fromkeys(titulares))
    if len(patients) == 1:
        return patients[0], "linked_beneficiario"
    if not patients and len(holders) == 1:
        return holders[0], "linked_self"
    if not patients and not holders:
        return None, "nobody"
    return None, "review_ambiguous"


def _status(kind: str, code: str | None, cohort: str) -> str:
    if kind != "estudio":
        return "matched"
    if cohort in {"review_ambiguous", "nobody"}:
        return "review"
    if not code:
        return "unmatched"
    return "matched"


def _label(kind: str, code: str | None, raw: str, document_type: str) -> str:
    if kind != "estudio":
        text = " ".join((raw or "").split())
        return (text or document_type)[:120]
    context = "fiscal_line" if document_type == "factura_fiscal" else "report_title"
    detail = specific_name(raw, code, context=context)
    if detail:
        return detail[:120]
    if document_type == "laboratorio":
        return "Laboratorio"
    if document_type == "imagenologia":
        return "Imagenología"
    return "Estudio"


def collect(cur) -> tuple[list[dict], list[tuple], Counter]:
    cur.execute(PAGE_SQL, (list(TYPES),))
    pages = cur.fetchall()
    cur.execute(PERSON_SQL)
    people: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"beneficiario": [], "titular": []})
    for row in cur.fetchall():
        people[row["invoice_id"]][row["role"]].append(row["person_id"])
    resolved: dict[str, tuple[str | None, str]] = {}

    def patient_of(invoice_id: str) -> tuple[str | None, str]:
        if invoice_id not in resolved:
            bucket = people.get(invoice_id) or {"beneficiario": [], "titular": []}
            resolved[invoice_id] = resolve_patient(bucket["beneficiario"], bucket["titular"])
        return resolved[invoice_id]

    by_path: dict[str, list[dict]] = defaultdict(list)
    for row in pages:
        by_path[row["backup_path"]].append(row)

    stats: Counter = Counter()
    rows: list[dict] = []
    observations: list[tuple] = []
    ids = None
    families: dict[str, set[str]] = defaultdict(set)
    estudio_invoices: set[str] = set()
    leaks: set[str] = set()
    cohort_invoices: dict[str, set[str]] = defaultdict(set)

    for path, docs in by_path.items():
        cache = cache_path(path)
        if not cache.is_file():
            stats["missing_cache"] += len(docs)
            continue
        data = json.loads(cache.read_text(encoding="utf-8"))
        for doc in docs:
            text = _page_text(data, doc["page_index"])
            if not text:
                stats["empty_ocr"] += 1
                continue
            invoice_id = doc["invoice_id"]
            number = doc["invoice_number"]
            person_id, cohort = patient_of(invoice_id)
            dtype = doc["document_type"]
            found: list[tuple[str, int, str, str | None]] = []
            if dtype == "factura_fiscal":
                services = extract(text).services
                if not services:
                    stats["fiscal_no_service"] += 1
                for line_no, service in enumerate(services):
                    kind, code = classify_line(service)
                    if kind == "skip":
                        stats["skipped_line"] += 1
                        if ids is None:
                            ids = load_ids(cur)
                        matches = normalize_text(service, "fiscal_line")
                        observations.extend(
                            observation_rows(
                                [m for m in matches if m.method == "none"],
                                f"fiscal:{doc['document_id']}#{line_no}",
                                ids,
                            )
                        )
                        continue
                    found.append((kind, line_no, service, code))
            elif dtype == "orden_servicio":
                order = classify_order(text)
                if order:
                    _kind, code, _state = order
                    found.append(("estudio", 0, "\n".join(text.splitlines()[:40]), code))
                    stats["study_order" if code else "study_order_unnamed"] += 1
                else:
                    stats["consult_order"] += 1
            else:
                result = classify_result_page(text, dtype)
                if result:
                    _kind, code = result
                    found.append(("estudio", 0, "\n".join(text.splitlines()[:20]), code))
                    stats["result_typed" if dtype in {"laboratorio", "imagenologia"} else "result_misfiled"] += 1
                elif dtype == "informe_medico":
                    stats["consult_or_other_note"] += 1

            for kind, line_no, raw, code in found:
                stats[f"kind:{kind}"] += 1
                if kind == "estudio":
                    estudio_invoices.add(number or invoice_id)
                    cohort_invoices[cohort].add(invoice_id)
                    families[number or invoice_id].add(family_of(code) or "sin_procedimiento")
                    if number in CONSULT_ONLY:
                        leaks.add(number)
                rows.append(
                    {
                        "invoice_id": invoice_id,
                        "document_id": doc["document_id"],
                        "source": "fiscal_line" if dtype == "factura_fiscal" else (
                            "study_order" if dtype == "orden_servicio" else "result_page"
                        ),
                        "line_no": line_no,
                        "service_label": _label(kind, code, raw, dtype),
                        "kind": kind,
                        "code": code,
                        "person_id": person_id,
                        "link_status": _status(kind, code, cohort),
                    }
                )
    stats["estudio_invoices"] = len(estudio_invoices)
    stats["consult_only_leaks"] = len(leaks)
    for cohort, invoices in cohort_invoices.items():
        stats[cohort] = len(invoices)
    family_counts: Counter = Counter()
    for fams in families.values():
        for fam in fams:
            family_counts[fam] += 1
    for fam, n in family_counts.items():
        stats[f"family:{fam}"] = n
    return rows, observations, stats


def _write_provenance(cur, rows: list[dict], stored: dict) -> None:
    """Queue field provenance in batches. One record() per row would wait on Neon each time."""
    pending: list[dict] = []
    for row in rows:
        key = (row["invoice_id"], row["source"], row["document_id"], row["line_no"])
        saved = stored.get(key)
        if not saved:
            continue
        ref = f"{row['source']}:{row['document_id']}#{row['line_no']}"
        base = {
            "entity": "invoice_service",
            "entity_id": saved["id"],
            "old": None,
            "rule_id": "estudio_extract",
            "source_kind": "ocr",
            "source_ref": ref,
        }
        pending.append({**base, "field": "kind", "new": row["kind"]})
        if saved["procedimiento_id"]:
            pending.append({**base, "field": "procedimiento_id", "new": saved["procedimiento_id"]})
        pending.append({**base, "field": "link_status", "new": row["link_status"]})
        if row["person_id"]:
            pending.append({**base, "field": "person_id", "new": row["person_id"]})
    for start in range(0, len(pending), 2000):
        with cur.connection.pipeline():
            for item in pending[start : start + 2000]:
                provenance.record(cur, **item)


def _gate(stats: Counter) -> str | None:
    if stats["consult_only_leaks"]:
        return "consult-only factura gained an estudio"
    if stats["estudio_invoices"] < MIN_ESTUDIO_INVOICES:
        return f"estudio invoices {stats['estudio_invoices']} below {MIN_ESTUDIO_INVOICES}"
    linked = stats["linked_beneficiario"] + stats["linked_self"]
    if linked < MIN_LINKED_INVOICES:
        return f"clear patient cohort {linked} below {MIN_LINKED_INVOICES}"
    return None


def apply_rows(cur, rows: list[dict], observations: list[tuple]) -> None:
    ids = load_ids(cur)
    missing = sorted({row["code"] for row in rows if row["code"] and row["code"] not in ids.procedimiento})
    if missing:
        raise SystemExit("procedimiento missing from Neon: " + ", ".join(missing))
    cur.execute("DELETE FROM avila.invoice_service")
    provenance.counters["replaced"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    payload = []
    for row in rows:
        proc = ids.procedimiento.get(row["code"]) if row["code"] else None
        esp_code = (default_catalog().procedimientos.get(row["code"] or "") or {}).get("especialidad_code")
        esp = ids.especialidad.get(esp_code) if esp_code else None
        payload.append(
            (
                row["invoice_id"],
                row["document_id"],
                row["source"],
                row["line_no"],
                row["service_label"],
                row["kind"],
                proc,
                esp,
                row["link_status"],
                row["person_id"],
                provenance.current_run_id(),
            )
        )
    with cur.connection.pipeline():
        cur.executemany(
            """
            INSERT INTO avila.invoice_service (
              invoice_id, document_id, source, line_no, service_label, kind,
              procedimiento_id, especialidad_id, link_status, person_id, run_id
            ) VALUES (
              %s::uuid, %s::uuid, %s, %s, %s, %s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid
            )
            """,
            payload,
        )
    cur.execute(
        """
        SELECT id::text AS id, invoice_id::text AS invoice_id, document_id::text AS document_id,
               source, line_no, kind, procedimiento_id::text AS procedimiento_id, link_status
        FROM avila.invoice_service
        """
    )
    stored = {(r["invoice_id"], r["source"], r["document_id"], r["line_no"]): r for r in cur.fetchall()}
    _write_provenance(cur, rows, stored)
    write_observations(cur, observations)
    cur.execute("SELECT avila.rebuild_estudios(%s::uuid)", (provenance.current_run_id(),))
    cur.execute(
        """
        SELECT
          (SELECT count(*)::int FROM avila.estudio) AS estudios,
          (SELECT count(*)::int FROM avila.estudio_archivo WHERE origen = 'documentacion') AS documentacion,
          (SELECT count(*)::int FROM avila.estudio_archivo WHERE origen = 'imagen') AS imagenes
        """
    )
    saved = cur.fetchone()
    provenance.counters.update(assign_catalog(cur))
    provenance.counters["estudios"] = saved["estudios"]
    provenance.counters["estudio_documentacion"] = saved["documentacion"]
    provenance.counters["estudio_imagenes"] = saved["imagenes"]
    provenance.counters["rows"] = len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL_UNPOOLED missing from .env")
    provenance.start_run(url, "estudio_extract", vars(args), apply=args.apply)
    reason = None
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        rows, observations, stats = collect(cur)
        provenance.counters.update(stats)
        reason = _gate(stats)
        if args.apply and reason:
            conn.rollback()
        elif args.apply:
            apply_rows(cur, rows, observations)
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url)
    print("apply" if args.apply and not reason else "dry-run", dict(sorted((k, v) for k, v in provenance.counters.items() if not str(k).startswith("prov:"))), flush=True)
    if reason:
        sys.exit(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
