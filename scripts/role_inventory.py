#!/usr/bin/env python3
"""Counts-only role linkage inventory (no PHI).

Writes markdown under output/runs/ and prints a JSON summary.

  PYTHONPATH=scripts .venv/bin/python scripts/role_inventory.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_load import load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "runs"

IDENTITY_TYPES = (
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
)


def collect(cur) -> dict:
    cur.execute(
        """
        SELECT
          (SELECT count(*) FROM avila.person) AS persons,
          (SELECT count(*) FROM avila.person
             WHERE coalesce(identity_number,'') <> '') AS persons_with_ci,
          (SELECT count(*) FROM avila.invoice) AS invoices,
          (SELECT count(*) FROM avila.invoice_person WHERE role='titular') AS titular_links,
          (SELECT count(*) FROM avila.invoice_person WHERE role='beneficiario') AS beneficiario_links,
          (SELECT count(*) FROM avila.invoice_person WHERE role='unknown') AS unknown_links
        """
    )
    out = dict(cur.fetchone())

    cur.execute(
        """
        SELECT
          count(*) FILTER (
            WHERE NOT EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )
          ) AS invoices_no_titular,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            ) AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person bip
              WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
            )
          ) AS invoices_titular_only,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            ) AND EXISTS (
              SELECT 1 FROM avila.invoice_person bip
              WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
            )
          ) AS invoices_titular_and_beneficiario,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM (
                SELECT invoice_id FROM avila.invoice_person
                WHERE role = 'titular' GROUP BY invoice_id HAVING count(*) > 1
              ) m WHERE m.invoice_id = i.id
            )
          ) AS invoices_multi_titular
        FROM avila.invoice i
        """
    )
    out.update(dict(cur.fetchone()))

    cur.execute(
        """
        SELECT
          count(*) FILTER (
            WHERE fiscal_extracted_at IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM avila.invoice_person tip
                WHERE tip.invoice_id = i.id AND tip.role = 'titular'
              )
          ) AS fiscal_filled_no_titular,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.document d
              WHERE d.invoice_id = i.id
                AND d.document_type::text = ANY(%s)
            )
            AND EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              JOIN avila.person p ON p.id = tip.person_id
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
                AND coalesce(p.identity_number,'') = ''
            )
          ) AS id_docs_titular_no_ci
        FROM avila.invoice i
        """,
        (list(IDENTITY_TYPES),),
    )
    out.update(dict(cur.fetchone()))

    cur.execute(
        """
        SELECT source, count(*)::int AS n
        FROM avila.invoice_person WHERE role = 'titular'
        GROUP BY 1 ORDER BY n DESC
        """
    )
    out["titular_by_source"] = {r["source"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT coalesce(parentesco, '(null)') AS parentesco, count(*)::int AS n
        FROM avila.invoice_person WHERE role = 'beneficiario'
        GROUP BY 1 ORDER BY n DESC
        """
    )
    out["beneficiario_parentesco"] = {r["parentesco"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT kind, status, count(*)::int AS n
        FROM avila.review_item
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    )
    out["reviews"] = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        SELECT
          count(*)::int AS auth_lines,
          count(*) FILTER (WHERE person_id IS NOT NULL)::int AS auth_with_person,
          count(*) FILTER (WHERE invoice_id IS NOT NULL)::int AS auth_with_invoice,
          count(*) FILTER (WHERE person_id IS NOT NULL AND invoice_id IS NULL)::int AS auth_person_no_invoice
        FROM avila.authorization_line
        """
    )
    out.update(dict(cur.fetchone()))

    cur.execute(
        """
        SELECT count(DISTINCT tip.person_id)::int AS ci_titulares_with_beneficiario
        FROM avila.invoice_person tip
        JOIN avila.person p ON p.id = tip.person_id
        WHERE tip.role = 'titular'
          AND coalesce(p.identity_number,'') <> ''
          AND EXISTS (
            SELECT 1 FROM avila.invoice_person bip
            WHERE bip.invoice_id = tip.invoice_id AND bip.role = 'beneficiario'
          )
        """
    )
    out.update(dict(cur.fetchone()))
    return out


def render_md(stats: dict) -> str:
    inv = stats["invoices"] or 1
    lines = [
        "# Role linkage inventory",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Persons | {stats['persons']} |",
        f"| Persons with CI | {stats['persons_with_ci']} |",
        f"| Invoices | {stats['invoices']} |",
        f"| Titular links | {stats['titular_links']} |",
        f"| Beneficiario links | {stats['beneficiario_links']} |",
        f"| Unknown links | {stats['unknown_links']} |",
        "",
        "## Invoice cohorts",
        "",
        "| Cohort | Count | % of invoices |",
        "| --- | ---: | ---: |",
        f"| No titular | {stats['invoices_no_titular']} | {100 * stats['invoices_no_titular'] // inv} |",
        f"| Titular only | {stats['invoices_titular_only']} | {100 * stats['invoices_titular_only'] // inv} |",
        f"| Titular + beneficiario | {stats['invoices_titular_and_beneficiario']} | {100 * stats['invoices_titular_and_beneficiario'] // inv} |",
        f"| Multi titular | {stats['invoices_multi_titular']} | {100 * stats['invoices_multi_titular'] // inv} |",
        f"| Fiscal filled, no titular | {stats['fiscal_filled_no_titular']} | {100 * stats['fiscal_filled_no_titular'] // inv} |",
        f"| ID docs, titular no CI | {stats['id_docs_titular_no_ci']} | {100 * stats['id_docs_titular_no_ci'] // inv} |",
        f"| CI titulares with beneficiario | {stats['ci_titulares_with_beneficiario']} | — |",
        "",
        "## Titular by source",
        "",
        "| Source | Count |",
        "| --- | ---: |",
    ]
    for src, n in (stats.get("titular_by_source") or {}).items():
        lines.append(f"| {src} | {n} |")
    lines += [
        "",
        "## Beneficiario parentesco",
        "",
        "| Parentesco | Count |",
        "| --- | ---: |",
    ]
    for src, n in (stats.get("beneficiario_parentesco") or {}).items():
        lines.append(f"| {src} | {n} |")
    lines += [
        "",
        "## Review items",
        "",
        "| Kind | Status | Count |",
        "| --- | --- | ---: |",
    ]
    for r in stats.get("reviews") or []:
        lines.append(f"| {r['kind']} | {r['status']} | {r['n']} |")
    lines += [
        "",
        "## Authorization lines",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total | {stats['auth_lines']} |",
        f"| With person | {stats['auth_with_person']} |",
        f"| With invoice | {stats['auth_with_invoice']} |",
        f"| Person but no invoice | {stats['auth_person_no_invoice']} |",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        stats = collect(cur)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"role-inventory-{stamp}.md"
    path.write_text(render_md(stats), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, default=str))
    print(f"wrote {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
