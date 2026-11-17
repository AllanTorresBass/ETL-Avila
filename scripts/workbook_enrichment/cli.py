"""CLI: discover / dry-run / apply workbook enrichment."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import provenance  # noqa: E402
from workbook_enrichment.db import connect, database_url, find_invoice_id  # noqa: E402
from workbook_enrichment.discover import (  # noqa: E402
    BACKUP,
    discover,
    iter_normalized_rows,
    iter_workbook_paths,
    write_inventory_csv,
)
from workbook_enrichment.link_roles import apply_row_links  # noqa: E402
from workbook_enrichment.load_authorization_lines import (  # noqa: E402
    upsert_authorization_line,
)
from workbook_enrichment.upsert_persons import resolve_people_from_row  # noqa: E402


def cmd_inventory(args: argparse.Namespace) -> None:
    hits = discover(BACKUP, limit=args.limit)
    out = Path(args.out)
    write_inventory_csv(hits, out)
    families = Counter(h.family for h in hits)
    sheets = sum(len(h.sheets) for h in hits)
    print(f"Workbooks: {len(hits)} sheets_with_headers: {sheets}")
    print("Families:", dict(families))
    print(f"Wrote {out}")


def _process_row(cur, relative, sheet, row_number, row, dry_run: bool, stats: Counter) -> None:
    people = resolve_people_from_row(cur, row, dry_run=dry_run)
    for act in people["actions"]:
        stats[act] += 1
    invoice_id = find_invoice_id(cur, row.get("invoice_number"))
    stats["invoice_matched" if invoice_id else "invoice_unmatched"] += 1
    for act in apply_row_links(cur, invoice_id=invoice_id, people=people, row=row, dry_run=dry_run):
        stats[f"link:{act}"] += 1
    person_for_line = people.get("beneficiario_id") or people.get("titular_id")
    act = upsert_authorization_line(
        cur,
        row=row,
        source_file=relative,
        sheet=sheet,
        row_number=row_number,
        invoice_id=invoice_id,
        person_id=person_for_line,
        dry_run=dry_run,
    )
    stats[f"line:{act}"] += 1


def cmd_run(args: argparse.Namespace) -> None:
    dry_run = not args.apply
    stats: Counter[str] = Counter()
    paths = list(iter_workbook_paths(BACKUP))
    if args.family:
        from workbook_enrichment.canonical import guess_family

        paths = [p for p in paths if guess_family(str(p.relative_to(BACKUP)), []) == args.family]
    if args.limit:
        paths = paths[: args.limit]
    if args.path:
        paths = [BACKUP / args.path]

    conn = connect()
    provenance.start_run(
        database_url(),
        "workbook_enrichment.run",
        {k: v for k, v in vars(args).items() if k != "func"},
        apply=not dry_run,
    )
    try:
        with conn.cursor() as cur:
            for index, path in enumerate(paths, start=1):
                relative = str(path.relative_to(BACKUP))
                stats["files"] += 1
                file_rows = 0
                try:
                    for sheet, row_number, row in iter_normalized_rows(path, relative):
                        stats["rows"] += 1
                        file_rows += 1
                        with provenance.source("workbook", f"{relative}:{sheet}:{row_number}"):
                            _process_row(cur, relative, sheet, row_number, row, dry_run, stats)
                except Exception as exc:  # noqa: BLE001
                    stats["file_errors"] += 1
                    print(f"ERROR {relative}: {exc}", flush=True)
                if index == 1 or index % 5 == 0 or index == len(paths):
                    print(
                        f"File {index}/{len(paths)} rows+={file_rows} total_rows={stats['rows']}",
                        flush=True,
                    )
                if not dry_run and index % 5 == 0:
                    conn.commit()
                    print(f"Committed through file {index}/{len(paths)}", flush=True)
            if not dry_run:
                conn.commit()
            elif dry_run:
                conn.rollback()
    finally:
        conn.close()
        provenance.finish_run(database_url(), dict(stats))

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "stats": dict(stats),
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ávila workbook person enrichment")
    sub = parser.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="Write workbook inventory CSV")
    inv.add_argument("--limit", type=int, default=0)
    inv.add_argument(
        "--out",
        default=str(ROOT / "output" / "invoices" / "workbook-inventory.csv"),
    )
    inv.set_defaults(func=cmd_inventory)

    run = sub.add_parser("run", help="Dry-run or apply enrichment")
    run.add_argument("--apply", action="store_true", help="Write to Neon")
    run.add_argument("--limit", type=int, default=0, help="Max workbook files")
    run.add_argument("--family", type=str, default="", help="Filter: sabana|claves|relacion|amp|cintillo")
    run.add_argument("--path", type=str, default="", help="Single relative backup path")
    run.add_argument(
        "--report",
        default=str(ROOT / "output" / "invoices" / "workbook-enrichment-report.json"),
    )
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
