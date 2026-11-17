#!/usr/bin/env python3
"""Corpus role linkage: beneficiario harvest, pair propagation, workbook relink.

Subcommands (dry-run by default; pass ``--apply`` to commit):

  beneficiario  — fiscal patient + FACT path name on titular-only invoices
  propagate     — copy known titular↔beneficiario pairs onto other FACTs of the same titular
  workbook      — re-apply sabana titular/beneficiario rows whose FACT now exists
  all           — beneficiario → propagate → workbook

Every write goes through provenance + try_promote / link_invoice_person.

  PYTHONPATH=scripts .venv/bin/python scripts/role_linkage.py beneficiario
  PYTHONPATH=scripts .venv/bin/python scripts/role_linkage.py all --apply --limit 200
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from document_types import extract_titular_from_path  # noqa: E402
from env_load import load_env  # noqa: E402
from fiscal_extract import FiscalFields, extract, link_fiscal_roles  # noqa: E402
from ocr_invoice_pages import _read_cache  # noqa: E402
from person_upsert import fold_person_name  # noqa: E402
from upload_documents_to_blob import (  # noqa: E402
    _link_path_name_as_beneficiario,
    _names_refer_to_same_person,
    link_invoice_person,
)
from workbook_enrichment.canonical import guess_family  # noqa: E402
from workbook_enrichment.db import find_invoice_id  # noqa: E402
from workbook_enrichment.discover import BACKUP, iter_normalized_rows, iter_workbook_paths  # noqa: E402
from workbook_enrichment.link_roles import apply_row_links  # noqa: E402
from workbook_enrichment.upsert_persons import resolve_people_from_row  # noqa: E402


def _titular_only_invoices(cur, limit: int = 0) -> list[dict]:
    cur.execute(
        """
        SELECT i.id::text AS invoice_id, i.invoice_number
        FROM avila.invoice i
        WHERE EXISTS (
          SELECT 1 FROM avila.invoice_person tip
          WHERE tip.invoice_id = i.id AND tip.role = 'titular'
        )
        AND NOT EXISTS (
          SELECT 1 FROM avila.invoice_person bip
          WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
        )
        ORDER BY i.invoice_number
        """
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    return cur.fetchall()


def _fiscal_fields_for_invoice(cur, invoice_id: str) -> FiscalFields:
    cur.execute(
        """
        SELECT d.page_index, sf.backup_path
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.invoice_id = %s::uuid
          AND d.document_type = 'factura_fiscal'
          AND d.page_index < 900
        ORDER BY sf.backup_path, d.page_index
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
    return fields


def _backup_path(cur, invoice_id: str) -> str | None:
    cur.execute(
        """
        SELECT sf.backup_path
        FROM avila.document d
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.invoice_id = %s::uuid
        ORDER BY d.page_index NULLS LAST, sf.backup_path
        LIMIT 1
        """,
        (invoice_id,),
    )
    row = cur.fetchone()
    return row["backup_path"] if row else None


def _titular_person(cur, invoice_id: str) -> dict | None:
    cur.execute(
        """
        SELECT p.id::text AS id, p.full_name, p.identity_number
        FROM avila.invoice_person tip
        JOIN avila.person p ON p.id = tip.person_id
        WHERE tip.invoice_id = %s::uuid AND tip.role = 'titular'
        LIMIT 1
        """,
        (invoice_id,),
    )
    return cur.fetchone()


def cmd_beneficiario(cur, *, apply: bool, limit: int, stats: Counter, conn=None) -> None:
    """Harvest beneficiarios from fiscal patient + path name on titular-only invoices."""
    for inv in _titular_only_invoices(cur, limit):
        stats["candidates"] += 1
        invoice_id = inv["invoice_id"]
        titular = _titular_person(cur, invoice_id)
        if not titular:
            stats["skip_no_titular"] += 1
            continue
        fields = _fiscal_fields_for_invoice(cur, invoice_id)
        backup = _backup_path(cur, invoice_id)
        path_name, path_ci = extract_titular_from_path(backup or "")
        with provenance.source("ocr", f"role_linkage.beneficiario:{inv['invoice_number']}"):
            before = stats["patient_linked"] + stats["path_linked"]
            if fields.patient_name or fields.patient_ci:
                role_stats: Counter = Counter()
                # Ensure titular_ci is set so patient≠titular comparison works.
                if not fields.titular_ci and titular.get("identity_number"):
                    fields.titular_ci = titular["identity_number"]
                if not fields.titular_name and titular.get("full_name"):
                    fields.titular_name = titular["full_name"]
                if apply:
                    link_fiscal_roles(cur, invoice_id, fields, role_stats)
                else:
                    patient_is_titular = bool(
                        fields.patient_ci and fields.patient_ci == fields.titular_ci
                    ) or bool(
                        fields.patient_name
                        and fields.titular_name
                        and _names_refer_to_same_person(fields.patient_name, fields.titular_name)
                    )
                    if fields.patient_name and not patient_is_titular:
                        role_stats["patient_linked"] += 1
                stats["patient_linked"] += role_stats.get("patient_linked", 0)
                for key, n in role_stats.items():
                    if key.startswith("titular:"):
                        stats[key] += n
            # Path patient when still no beneficiario after fiscal.
            cur.execute(
                """
                SELECT 1 FROM avila.invoice_person
                WHERE invoice_id = %s::uuid AND role = 'beneficiario' LIMIT 1
                """,
                (invoice_id,),
            )
            has_ben = cur.fetchone() is not None
            if not has_ben and path_name:
                if apply:
                    linked = _link_path_name_as_beneficiario(
                        cur, invoice_id, path_name, titular["id"], path_ci=path_ci
                    )
                    if linked:
                        stats["path_linked"] += 1
                    else:
                        stats["path_skipped"] += 1
                else:
                    if _names_refer_to_same_person(path_name, titular.get("full_name") or ""):
                        stats["path_skipped"] += 1
                    elif path_ci and path_ci == (titular.get("identity_number") or ""):
                        stats["path_skipped"] += 1
                    else:
                        stats["path_linked"] += 1
            elif has_ben and before == stats["patient_linked"] + stats["path_linked"]:
                stats["already_had_beneficiario"] += 1
            if stats["patient_linked"] + stats["path_linked"] == before:
                stats["no_signal"] += 1
        if apply and conn is not None and stats["candidates"] % 200 == 0:
            conn.commit()
            print(
                f"beneficiario progress candidates={stats['candidates']} "
                f"path={stats['path_linked']} patient={stats['patient_linked']} "
                f"no_signal={stats['no_signal']}",
                flush=True,
            )


def cmd_propagate(cur, *, apply: bool, limit: int, stats: Counter) -> None:
    """Propagate known titular↔beneficiario pairs onto other invoices of the same titular."""
    cur.execute(
        """
        SELECT tip.person_id::text AS titular_id,
               bip.person_id::text AS beneficiario_id,
               max(bip.parentesco) AS parentesco,
               count(*)::int AS pair_count
        FROM avila.invoice_person tip
        JOIN avila.invoice_person bip
          ON bip.invoice_id = tip.invoice_id AND bip.role = 'beneficiario'
        WHERE tip.role = 'titular' AND tip.person_id <> bip.person_id
        GROUP BY tip.person_id, bip.person_id
        HAVING count(*) >= 1
        ORDER BY pair_count DESC
        """
    )
    pairs = cur.fetchall()
    stats["pairs"] = len(pairs)
    linked = 0
    for pair in pairs:
        if limit and linked >= limit:
            break
        cur.execute(
            """
            SELECT i.id::text AS invoice_id, i.invoice_number
            FROM avila.invoice_person tip
            JOIN avila.invoice i ON i.id = tip.invoice_id
            WHERE tip.person_id = %s::uuid AND tip.role = 'titular'
              AND NOT EXISTS (
                SELECT 1 FROM avila.invoice_person x
                WHERE x.invoice_id = tip.invoice_id AND x.person_id = %s::uuid
              )
              AND NOT EXISTS (
                SELECT 1 FROM avila.invoice_person bip
                WHERE bip.invoice_id = tip.invoice_id AND bip.role = 'beneficiario'
              )
            ORDER BY i.invoice_number
            """,
            (pair["titular_id"], pair["beneficiario_id"]),
        )
        targets = cur.fetchall()
        if not targets:
            stats["pair_no_targets"] += 1
            continue
        cur.execute(
            "SELECT full_name, identity_number FROM avila.person WHERE id = %s::uuid",
            (pair["beneficiario_id"],),
        )
        ben = cur.fetchone() or {}
        ben_name = ben.get("full_name") or ""
        ben_ci = ben.get("identity_number") or ""
        for inv in targets:
            if limit and linked >= limit:
                break
            stats["propagate_candidates"] += 1
            fields = _fiscal_fields_for_invoice(cur, inv["invoice_id"])
            backup = _backup_path(cur, inv["invoice_id"])
            path_name, path_ci = extract_titular_from_path(backup or "")
            evidence = False
            if ben_ci and fields.patient_ci and fields.patient_ci == ben_ci:
                evidence = True
                stats["evidence_patient_ci"] += 1
            elif ben_name and fields.patient_name and _names_refer_to_same_person(
                ben_name, fields.patient_name
            ):
                evidence = True
                stats["evidence_patient_name"] += 1
            elif ben_name and path_name and _names_refer_to_same_person(ben_name, path_name):
                evidence = True
                stats["evidence_path_name"] += 1
            elif ben_ci and path_ci and ben_ci == path_ci:
                evidence = True
                stats["evidence_path_ci"] += 1
            if not evidence:
                stats["propagate_no_evidence"] += 1
                continue
            with provenance.source("derived", f"pair_propagate:{inv['invoice_number']}"):
                if apply:
                    link_invoice_person(
                        cur,
                        inv["invoice_id"],
                        pair["beneficiario_id"],
                        "beneficiario",
                        parentesco=pair.get("parentesco"),
                        source="resolver",
                        rule_id="pair_propagate",
                    )
                stats["propagate_linked"] += 1
                linked += 1


def cmd_workbook(cur, *, apply: bool, limit: int, stats: Counter) -> None:
    """Re-link sabana/relacion workbook rows whose FACT invoice now exists in Neon."""
    processed = 0
    for path in iter_workbook_paths(BACKUP):
        relative = str(path.relative_to(BACKUP))
        family = guess_family(relative, [])
        if family not in {"sabana", "relacion", "amp"}:
            continue
        try:
            rows_iter = iter_normalized_rows(path, relative)
        except Exception:  # noqa: BLE001
            stats["workbook_read_error"] += 1
            continue
        for sheet, row_number, row in rows_iter:
            if limit and processed >= limit:
                return
            if not row.get("invoice_number"):
                continue
            if not row.get("titular_ci") and not row.get("titular_name"):
                continue
            if not row.get("beneficiario_name") and not row.get("beneficiario_ci"):
                continue
            same = False
            if row.get("beneficiario_ci") and row.get("titular_ci"):
                same = row["beneficiario_ci"] == row["titular_ci"]
            elif row.get("beneficiario_name") and row.get("titular_name"):
                same = fold_person_name(row["beneficiario_name"]) == fold_person_name(
                    row["titular_name"]
                )
            if same:
                continue
            invoice_id = find_invoice_id(cur, row.get("invoice_number"))
            if not invoice_id:
                stats["workbook_invoice_missing"] += 1
                continue
            cur.execute(
                """
                SELECT 1 FROM avila.invoice_person
                WHERE invoice_id = %s::uuid AND role = 'beneficiario' LIMIT 1
                """,
                (invoice_id,),
            )
            if cur.fetchone():
                stats["workbook_already_linked"] += 1
                continue
            stats["workbook_candidates"] += 1
            processed += 1
            with provenance.source("workbook", f"{relative}:{sheet}:{row_number}"):
                people = resolve_people_from_row(cur, row, dry_run=not apply)
                actions = apply_row_links(
                    cur,
                    invoice_id=invoice_id if apply else None,
                    people=people,
                    row=row,
                    dry_run=not apply,
                )
                if apply:
                    for action in actions:
                        stats[f"workbook_{action}"] += 1
                    stats["workbook_linked"] += 1
                else:
                    stats["workbook_would_link"] += 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("beneficiario", "propagate", "workbook", "all"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, f"role_linkage.{args.command}", vars(args), apply=args.apply)
    stats: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        commands = (
            ("beneficiario", "propagate", "workbook")
            if args.command == "all"
            else (args.command,)
        )
        for name in commands:
            if name == "beneficiario":
                cmd_beneficiario(
                    cur, apply=args.apply, limit=args.limit, stats=stats, conn=conn if args.apply else None
                )
            elif name == "propagate":
                cmd_propagate(cur, apply=args.apply, limit=args.limit, stats=stats)
            elif name == "workbook":
                cmd_workbook(cur, apply=args.apply, limit=args.limit, stats=stats)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run", dict(sorted(stats.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
