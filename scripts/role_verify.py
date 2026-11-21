#!/usr/bin/env python3
"""Corpus titular/beneficiario verification — one cohort per invoice.

Measures evidence agreement (plastic CI, FACT path, fiscal patient, reviews)
and optionally runs auto-safe repairs for selected cohorts.

  PYTHONPATH=scripts .venv/bin/python scripts/role_verify.py
  PYTHONPATH=scripts .venv/bin/python scripts/role_verify.py --write-cohort
  PYTHONPATH=scripts .venv/bin/python scripts/role_verify.py --repair --limit 100
  PYTHONPATH=scripts .venv/bin/python scripts/role_verify.py --repair --apply --cohorts mismatch_no_beneficiario,nameless_titular

Stdout: JSON cohort counts (no PHI). Markdown under output/runs/.
PHI queue: output/persons/_queue/role-verify.jsonl (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from document_types import (  # noqa: E402
    extract_name_from_cedula_ocr,
    extract_titular_from_path,
)
from env_load import load_env  # noqa: E402
from fiscal_extract import FiscalFields, extract, link_fiscal_roles  # noqa: E402
from ocr_invoice_pages import _read_cache  # noqa: E402
from person_upsert import upsert_by_ci  # noqa: E402
from role_cohorts import (  # noqa: E402
    ACTIONS,
    BLOCKING_REVIEW_KINDS,
    COHORTS,
    IDENTITY_DOC_TYPES,
    MISMATCH_FISCAL_ACTION,
    assign_cohort,
    empty_cohort_counts,
)
from upload_documents_to_blob import (  # noqa: E402
    _link_path_name_as_beneficiario,
    try_promote_ci_titular,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "runs"
QUEUE_DIR = ROOT / "output" / "persons" / "_queue"


def _load_invoice_rows(cur, limit: int = 0) -> list[dict]:
    """Set-based load — avoid correlated subqueries per invoice."""
    cur.execute(
        """
        WITH role_counts AS (
          SELECT
            invoice_id,
            count(*) FILTER (WHERE role = 'titular')::int AS titular_count,
            count(*) FILTER (WHERE role = 'beneficiario')::int AS beneficiario_count,
            count(*) FILTER (WHERE role = 'unknown')::int AS unknown_count
          FROM avila.invoice_person
          GROUP BY invoice_id
        ),
        titular_pick AS (
          SELECT DISTINCT ON (invoice_id)
            invoice_id, person_id, source
          FROM avila.invoice_person
          WHERE role = 'titular'
          ORDER BY invoice_id,
            CASE source
              WHEN 'workbook' THEN 0
              WHEN 'ocr_cedula' THEN 1
              WHEN 'fiscal_ocr' THEN 2
              ELSE 9
            END
        ),
        id_docs AS (
          SELECT DISTINCT invoice_id
          FROM avila.document
          WHERE document_type::text = ANY(%s)
        ),
        open_rev AS (
          SELECT invoice_id, array_agg(kind::text) AS kinds
          FROM avila.review_item
          WHERE status = 'open' AND kind::text = ANY(%s)
          GROUP BY invoice_id
        ),
        backup AS (
          SELECT DISTINCT ON (d.invoice_id)
            d.invoice_id, sf.backup_path
          FROM avila.document d
          JOIN avila.source_file sf ON sf.id = d.source_file_id
          WHERE d.invoice_id IS NOT NULL
          ORDER BY d.invoice_id, d.page_index NULLS LAST, sf.backup_path
        )
        SELECT
          i.id::text AS invoice_id,
          i.invoice_number,
          i.fiscal_extracted_at IS NOT NULL AS fiscal_filled,
          i.role_cohort AS prior_cohort,
          coalesce(rc.titular_count, 0) AS titular_count,
          coalesce(rc.beneficiario_count, 0) AS beneficiario_count,
          coalesce(rc.unknown_count, 0) AS unknown_count,
          (id.invoice_id IS NOT NULL) AS has_id_docs,
          coalesce(orv.kinds, ARRAY[]::text[]) AS open_reviews,
          tp.person_id::text AS titular_id,
          tp.source AS titular_source,
          p.full_name AS titular_name,
          p.identity_number AS titular_ci,
          b.backup_path
        FROM avila.invoice i
        LEFT JOIN role_counts rc ON rc.invoice_id = i.id
        LEFT JOIN titular_pick tp ON tp.invoice_id = i.id
        LEFT JOIN avila.person p ON p.id = tp.person_id
        LEFT JOIN id_docs id ON id.invoice_id = i.id
        LEFT JOIN open_rev orv ON orv.invoice_id = i.id
        LEFT JOIN backup b ON b.invoice_id = i.id
        ORDER BY i.invoice_number
        """
        + (f" LIMIT {int(limit)}" if limit else ""),
        (list(IDENTITY_DOC_TYPES), list(BLOCKING_REVIEW_KINDS)),
    )
    return cur.fetchall()


def _fiscal_patient(cur, invoice_id: str) -> tuple[str | None, str | None]:
    cur.execute(
        """
        SELECT d.page_index, sf.backup_path
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.invoice_id = %s::uuid
          AND d.document_type = 'factura_fiscal'
          AND d.page_index < 900
        ORDER BY sf.backup_path, d.page_index
        LIMIT 3
        """,
        (invoice_id,),
    )
    fields = FiscalFields()
    for row in cur.fetchall():
        cache = _read_cache(row["backup_path"])
        if not cache:
            continue
        pages = cache.get("pages") or []
        idx = int(row["page_index"]) - 1
        if 0 <= idx < len(pages):
            fields.merge(extract(pages[idx].get("text") or ""))
    return fields.patient_name, fields.patient_ci


def _cedula_name_from_pages(cur, invoice_id: str) -> str | None:
    cur.execute(
        """
        SELECT d.page_index, sf.backup_path
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.invoice_id = %s::uuid
          AND d.document_type::text = ANY(%s)
          AND d.page_index < 900
        ORDER BY
          CASE d.document_type::text
            WHEN 'cedula_identidad' THEN 0
            WHEN 'documentos_identificacion' THEN 1
            WHEN 'carnet' THEN 2
            ELSE 3
          END,
          d.page_index
        LIMIT 6
        """,
        (invoice_id, list(IDENTITY_DOC_TYPES)),
    )
    for row in cur.fetchall():
        cache = _read_cache(row["backup_path"])
        if not cache:
            continue
        pages = cache.get("pages") or []
        idx = int(row["page_index"]) - 1
        if 0 <= idx < len(pages):
            name = extract_name_from_cedula_ocr(pages[idx].get("text") or "")
            if name:
                return name
    return None


def build_signals(cur, row: dict, *, with_fiscal: bool) -> dict[str, Any]:
    path_name, path_ci = extract_titular_from_path(row.get("backup_path") or "")
    fiscal_patient_name = fiscal_patient_ci = None
    if with_fiscal:
        fiscal_patient_name, fiscal_patient_ci = _fiscal_patient(cur, row["invoice_id"])
    return {
        "invoice_id": row["invoice_id"],
        "invoice_number": row["invoice_number"],
        "titular_count": row["titular_count"] or 0,
        "beneficiario_count": row["beneficiario_count"] or 0,
        "unknown_count": row["unknown_count"] or 0,
        "has_id_docs": bool(row["has_id_docs"]),
        "open_reviews": list(row["open_reviews"] or []),
        "titular_id": row.get("titular_id"),
        "titular_name": row.get("titular_name"),
        "titular_ci": row.get("titular_ci"),
        "titular_source": row.get("titular_source"),
        "path_name": path_name,
        "path_ci": path_ci,
        "fiscal_patient_name": fiscal_patient_name,
        "fiscal_patient_ci": fiscal_patient_ci,
        "fiscal_filled": bool(row.get("fiscal_filled")),
    }


def classify_invoice(cur, row: dict, *, with_fiscal: bool) -> dict[str, Any]:
    """Classify one invoice. Path evidence is always used; fiscal OCR only when
    ``with_fiscal`` (slow — prefer for --repair of mismatch/no_titular cohorts).
    """
    signals = build_signals(cur, row, with_fiscal=with_fiscal)
    cohort, action = assign_cohort(signals)
    return {
        "invoice_id": signals["invoice_id"],
        "invoice_number": signals["invoice_number"],
        "cohort": cohort,
        "action": action,
        "titular_source": signals.get("titular_source"),
        "has_path": bool(signals.get("path_name") or signals.get("path_ci")),
        "has_fiscal_patient": bool(
            signals.get("fiscal_patient_name") or signals.get("fiscal_patient_ci")
        ),
        "has_id_docs": signals["has_id_docs"],
        "open_reviews": signals["open_reviews"],
        "beneficiario_count": signals["beneficiario_count"],
        "titular_count": signals["titular_count"],
        # PHI kept only for repair helpers / queue (git-ignored).
        "_titular_id": signals.get("titular_id"),
        "_titular_ci": signals.get("titular_ci"),
        "_titular_name": signals.get("titular_name"),
        "_path_name": signals.get("path_name"),
        "_path_ci": signals.get("path_ci"),
        "_fiscal_patient_name": signals.get("fiscal_patient_name"),
        "_fiscal_patient_ci": signals.get("fiscal_patient_ci"),
    }


def render_md(counts: dict[str, int], extras: dict[str, Any], invoices: int) -> str:
    inv = invoices or 1
    lines = [
        "# Role verification",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Cohorts (one primary per invoice)",
        "",
        "| Cohort | Count | % | Suggested action |",
        "| --- | ---: | ---: | --- |",
    ]
    for cohort in COHORTS:
        n = counts.get(cohort, 0)
        lines.append(
            f"| {cohort} | {n} | {100 * n // inv} | {ACTIONS.get(cohort, '')} |"
        )
    lines += [
        "",
        f"| **Total invoices** | **{invoices}** | 100 | — |",
        "",
        "## Extras",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, val in sorted(extras.items()):
        lines.append(f"| {key} | {val} |")
    lines.append("")
    return "\n".join(lines)


def _write_snapshot(cur, counts: dict[str, int], extras: dict[str, Any], invoices: int) -> None:
    payload = {
        "invoices": invoices,
        "cohorts": counts,
        **{f"extra_{k}": v for k, v in extras.items()},
        "mismatch_no_beneficiario": counts.get("mismatch_no_beneficiario", 0),
        "id_docs_no_ci": counts.get("id_docs_no_ci", 0),
        "nameless_titular": counts.get("nameless_titular", 0),
        "blocked_review": counts.get("blocked_review", 0),
        "multi_titular": counts.get("multi_titular", 0),
        "no_titular": counts.get("no_titular", 0),
        "resolved_pair": counts.get("resolved_pair", 0),
        "self_visit_ok": counts.get("self_visit_ok", 0),
    }
    cur.execute(
        """
        INSERT INTO avila.role_verify_snapshot (id, computed_at, counters)
        VALUES (1, now(), %s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
          computed_at = excluded.computed_at,
          counters = excluded.counters
        """,
        (json.dumps(payload),),
    )


def _write_cohort_column(cur, results: list[dict]) -> None:
    if not results:
        return
    ids = [r["invoice_id"] for r in results]
    cohorts = [r["cohort"] for r in results]
    cur.execute(
        """
        UPDATE avila.invoice AS i
        SET role_cohort = v.cohort
        FROM unnest(%s::uuid[], %s::text[]) AS v(invoice_id, cohort)
        WHERE i.id = v.invoice_id
        """,
        (ids, cohorts),
    )


def _queue_public(row: dict) -> dict:
    """Strip underscore PHI keys from the on-disk queue record… keep FACT + flags."""
    return {
        "invoice_number": row["invoice_number"],
        "invoice_id": row["invoice_id"],
        "cohort": row["cohort"],
        "action": row["action"],
        "has_path": row["has_path"],
        "has_fiscal_patient": row["has_fiscal_patient"],
        "has_id_docs": row["has_id_docs"],
        "open_reviews": row["open_reviews"],
        "beneficiario_count": row["beneficiario_count"],
        "titular_count": row["titular_count"],
        "titular_source": row.get("titular_source"),
    }


def repair_one(cur, row: dict, stats: Counter) -> None:
    """Auto-safe repairs only; blockers stay for /revision."""
    cohort = row["cohort"]
    action = row["action"]
    invoice_id = row["invoice_id"]
    stats[f"repair_attempt:{cohort}"] += 1

    if cohort == "blocked_review":
        stats["repair_skip_blocked"] += 1
        return

    if cohort == "nameless_titular":
        titular_id = row.get("_titular_id")
        titular_ci = row.get("_titular_ci")
        if not titular_id or not titular_ci:
            stats["repair_skip_no_titular"] += 1
            return
        name = _cedula_name_from_pages(cur, invoice_id)
        if not name and row.get("_path_name") and row.get("_path_ci") == titular_ci:
            name = row["_path_name"]
        if not name:
            stats["repair_nameless_no_ocr_name"] += 1
            return
        with provenance.source("ocr", f"role_verify.fill_name:{row['invoice_number']}"):
            upsert_by_ci(cur, identity_number=titular_ci, full_name=name, identity_type="cedula")
        stats["repair_filled_name"] += 1
        # Fall through: after naming, try path beneficiario when path differs.
        path_name = row.get("_path_name")
        path_ci = row.get("_path_ci")
        if path_name:
            linked = _link_path_name_as_beneficiario(
                cur, invoice_id, path_name, titular_id, path_ci=path_ci
            )
            if linked:
                stats["repair_path_after_name"] += 1
        return

    if cohort == "mismatch_no_beneficiario":
        titular_id = row.get("_titular_id")
        if not titular_id:
            stats["repair_skip_no_titular"] += 1
            return
        with provenance.source("ocr", f"role_verify.mismatch:{row['invoice_number']}"):
            fp_name = row.get("_fiscal_patient_name")
            fp_ci = row.get("_fiscal_patient_ci")
            if not fp_name and not fp_ci:
                fp_name, fp_ci = _fiscal_patient(cur, invoice_id)
            if fp_name or fp_ci:
                fields = FiscalFields(
                    patient_name=fp_name,
                    patient_ci=fp_ci,
                    titular_name=row.get("_titular_name"),
                    titular_ci=row.get("_titular_ci"),
                )
                role_stats: Counter = Counter()
                link_fiscal_roles(cur, invoice_id, fields, role_stats)
                if role_stats.get("patient_linked"):
                    stats["repair_fiscal_patient"] += 1
                    return
            path_name = row.get("_path_name")
            if path_name:
                linked = _link_path_name_as_beneficiario(
                    cur,
                    invoice_id,
                    path_name,
                    titular_id,
                    path_ci=row.get("_path_ci"),
                )
                if linked:
                    stats["repair_path_beneficiario"] += 1
                else:
                    stats["repair_path_skipped"] += 1
            else:
                stats["repair_mismatch_no_signal"] += 1
        return

    if cohort == "no_titular":
        # Fiscal tomador CI → try_promote when available from OCR cache.
        fields = FiscalFields()
        cur.execute(
            """
            SELECT d.page_index, sf.backup_path
            FROM avila.document d
            JOIN avila.source_file sf ON sf.id = d.source_file_id
            WHERE d.invoice_id = %s::uuid AND d.document_type = 'factura_fiscal'
            ORDER BY d.page_index LIMIT 2
            """,
            (invoice_id,),
        )
        for doc in cur.fetchall():
            cache = _read_cache(doc["backup_path"])
            if not cache:
                continue
            pages = cache.get("pages") or []
            idx = int(doc["page_index"]) - 1
            if 0 <= idx < len(pages):
                fields.merge(extract(pages[idx].get("text") or ""))
        if fields.titular_ci:
            with provenance.source("ocr", f"role_verify.no_titular:{row['invoice_number']}"):
                person_id, _ = upsert_by_ci(
                    cur,
                    identity_number=fields.titular_ci,
                    full_name=fields.titular_name,
                    identity_type="cedula",
                )
                if person_id:
                    outcome = try_promote_ci_titular(
                        cur,
                        invoice_id,
                        person_id,
                        path_name=row.get("_path_name"),
                        path_ci=row.get("_path_ci"),
                        source="fiscal_ocr",
                    )
                    stats[f"repair_promote:{outcome}"] += 1
                else:
                    stats["repair_no_titular_upsert_fail"] += 1
        else:
            stats["repair_no_titular_no_fiscal_ci"] += 1
        return

    stats["repair_noop"] += 1


def collect_structural(cur) -> dict[str, int]:
    """SQL-only cohorts readable without OCR (for inventory / view parity)."""
    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE role_cohort = 'multi_titular') AS multi_titular,
          count(*) FILTER (WHERE role_cohort = 'blocked_review') AS blocked_review,
          count(*) FILTER (WHERE role_cohort = 'no_titular') AS no_titular,
          count(*) FILTER (WHERE role_cohort = 'id_docs_no_ci') AS id_docs_no_ci,
          count(*) FILTER (WHERE role_cohort = 'mismatch_no_beneficiario') AS mismatch_no_beneficiario,
          count(*) FILTER (WHERE role_cohort = 'nameless_titular') AS nameless_titular,
          count(*) FILTER (WHERE role_cohort = 'self_visit_ok') AS self_visit_ok,
          count(*) FILTER (WHERE role_cohort = 'resolved_pair') AS resolved_pair,
          count(*) FILTER (WHERE role_cohort = 'unknown_links') AS unknown_links,
          count(*) FILTER (WHERE role_cohort = 'weak_evidence') AS weak_evidence,
          count(*) FILTER (WHERE role_cohort IS NULL) AS unset_cohort,
          count(*) AS invoices
        FROM avila.invoice
        """
    )
    return dict(cur.fetchone())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Cap invoices processed")
    parser.add_argument(
        "--write-cohort",
        action="store_true",
        help="Persist role_cohort on avila.invoice + snapshot counters",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Run auto-safe repairs for selected cohorts (dry-run unless --apply)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit repairs and cohort writes",
    )
    parser.add_argument(
        "--cohorts",
        default="",
        help="Comma-separated cohorts to repair (default: mismatch_no_beneficiario,nameless_titular,no_titular)",
    )
    parser.add_argument(
        "--with-fiscal",
        action="store_true",
        help="Always load fiscal OCR patient for every invoice (slower)",
    )
    parser.add_argument("--queue", action="store_true", help="Write role-verify.jsonl queue")
    args = parser.parse_args()

    repair_cohorts = {
        c.strip()
        for c in (args.cohorts or "mismatch_no_beneficiario,nameless_titular,no_titular").split(",")
        if c.strip()
    }

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    mode_apply = bool(args.apply and (args.repair or args.write_cohort))
    provenance.start_run(
        url,
        "role_verify",
        {
            "limit": args.limit,
            "repair": args.repair,
            "write_cohort": args.write_cohort,
            "cohorts": sorted(repair_cohorts),
        },
        apply=mode_apply,
    )

    counts = empty_cohort_counts()
    extras: Counter = Counter()
    results: list[dict] = []
    repair_stats: Counter = Counter()

    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        print("loading invoices…", file=sys.stderr, flush=True)
        rows = _load_invoice_rows(cur, limit=args.limit)
        extras["invoices_scanned"] = len(rows)
        print(f"classifying {len(rows)} invoices…", file=sys.stderr, flush=True)
        for idx, row in enumerate(rows, start=1):
            classified = classify_invoice(cur, row, with_fiscal=args.with_fiscal)
            counts[classified["cohort"]] += 1
            results.append(classified)
            if args.repair and classified["cohort"] in repair_cohorts:
                if args.apply:
                    repair_one(cur, classified, repair_stats)
                else:
                    repair_stats[f"would_repair:{classified['cohort']}"] += 1
            if idx % 2000 == 0:
                print(f"  …{idx}/{len(rows)}", file=sys.stderr, flush=True)

        if args.write_cohort and args.apply:
            print("writing role_cohort…", file=sys.stderr, flush=True)
            _write_cohort_column(cur, results)
            _write_snapshot(cur, counts, dict(repair_stats), len(rows))
            extras["cohort_column_written"] = len(results)

        if mode_apply:
            conn.commit()
        else:
            conn.rollback()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUT_DIR / f"role-verify-{stamp}.md"
    extras.update(repair_stats)
    md_path.write_text(render_md(counts, dict(extras), len(results)), encoding="utf-8")

    if args.queue or args.repair:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        queue_path = QUEUE_DIR / "role-verify.jsonl"
        with queue_path.open("w", encoding="utf-8") as fh:
            for row in results:
                if not args.repair or row["cohort"] in repair_cohorts or row["cohort"] in (
                    "blocked_review",
                    "id_docs_no_ci",
                    "multi_titular",
                ):
                    fh.write(json.dumps(_queue_public(row), ensure_ascii=False) + "\n")
        print(f"wrote {queue_path}", file=sys.stderr)

    summary = {
        "invoices": len(results),
        "cohorts": counts,
        "extras": dict(extras),
        "report": str(md_path),
    }
    provenance.finish_run(url, {"cohorts": counts, **dict(extras)})
    print(json.dumps(summary, ensure_ascii=False, default=str))
    print(f"wrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
