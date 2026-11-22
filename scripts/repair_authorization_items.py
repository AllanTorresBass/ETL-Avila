"""Turn each authorization line into one header, its items, and its workbook sources.

Dry-run unless ``--apply``. Does not create people, create facturas, change
``person_id``, or restore a role that invoice truth cleared. A second apply
does not insert a second item or source for the same workbook row.

Stdout is counts only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import provenance  # noqa: E402
from workbook_enrichment.authorization_items import (  # noqa: E402
    RequestCopy,
    aps_code_from_path,
    items_or_service,
    parse_request_items,
    partition_copies,
    source_ref,
)
from workbook_enrichment.db import connect, database_url  # noqa: E402
from workbook_enrichment.discover import BACKUP, find_header_row  # noqa: E402
from workbook_enrichment.normalize import digits_ci, row_dict  # noqa: E402


def _digits(value: str | None) -> str:
    return digits_ci(value) or ""


def _load_sheets(path: Path) -> dict[str, list[list]]:
    suffix = path.suffix.lower()
    if suffix == ".xls":
        import xlrd

        book = xlrd.open_workbook(str(path))
        sheets: dict[str, list[list]] = {}
        for sheet in book.sheets():
            rows: list[list] = []
            for r in range(sheet.nrows):
                converted = []
                for c in range(sheet.ncols):
                    value = sheet.cell_value(r, c)
                    if sheet.cell_type(r, c) == xlrd.XL_CELL_DATE and value not in ("", None):
                        try:
                            value = xlrd.xldate_as_datetime(value, book.datemode).date()
                        except Exception:  # noqa: BLE001
                            pass
                    converted.append(value)
                rows.append(converted)
            sheets[sheet.name] = rows
        return sheets
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(path, read_only=True, data_only=True)
        sheets = {}
        try:
            for name in book.sheetnames:
                sheets[name] = [list(row) for row in book[name].iter_rows(values_only=True)]
        finally:
            book.close()
        return sheets
    return {}


def _items_for(sheets: dict[str, list[list]], source_row: str, service_description: str | None):
    if ":" not in source_row:
        return items_or_service([], service_description, source_row), None
    sheet_name, row_text = source_row.rsplit(":", 1)
    if not row_text.isdigit():
        return items_or_service([], service_description, source_row), None
    rows = sheets.get(sheet_name)
    if rows is None:
        rows = sheets.get(sheet_name.strip())
    excel = int(row_text)
    if not rows:
        return items_or_service([], service_description, str(excel)), None
    header_index, headers = find_header_row(rows)
    data_index = excel - 1
    titular = None
    parsed = []
    if header_index >= 0 and 0 <= data_index < len(rows) and data_index > header_index:
        header_list = list(headers)
        titular = row_dict(header_list, list(rows[data_index])).get("titular_ci")
        parsed = parse_request_items(header_list, rows, data_index, sheet_name)
    return items_or_service(parsed, service_description, str(excel)), titular


def _people(cur) -> dict[str, str | None]:
    cur.execute(
        """
        SELECT id::text AS id, regexp_replace(identity_number, '\\D', '', 'g') AS ci
        FROM avila.person
        WHERE identity_number IS NOT NULL AND btrim(identity_number) <> ''
        """
    )
    found: dict[str, str | None] = {}
    for row in cur.fetchall():
        ci = row["ci"] or ""
        if not ci:
            continue
        if ci in found:
            found[ci] = None
        else:
            found[ci] = row["id"]
    return found


def _reviewed(cur) -> set[str]:
    cur.execute(
        """
        SELECT DISTINCT authorization_line_id::text AS id
        FROM avila.review_item
        WHERE authorization_line_id IS NOT NULL
        """
    )
    return {row["id"] for row in cur.fetchall()}


def _existing(cur) -> tuple[set[tuple[str, str]], set[str]]:
    cur.execute("SELECT authorization_line_id::text AS line_id, source_row FROM avila.authorization_item")
    items = {(row["line_id"], row["source_row"]) for row in cur.fetchall()}
    cur.execute("SELECT source_hash FROM avila.authorization_source")
    hashes = {row["source_hash"] for row in cur.fetchall()}
    return items, hashes


def repair(cur, apply: bool) -> dict[str, int]:
    people = _people(cur)
    reviewed = _reviewed(cur)
    have_items, have_hashes = _existing(cur)
    cur.execute(
        """
        SELECT al.id::text AS id, al.person_id::text AS person_id, al.source_file, al.source_row,
               al.source_hash, al.service_date, al.amount_bs, al.diagnosis, al.service_description,
               al.aps_code, al.invoice_id::text AS invoice_id, al.titular_person_id::text AS titular_person_id,
               al.duplicate_of::text AS duplicate_of, p.identity_number
        FROM avila.authorization_line al
        LEFT JOIN avila.person p ON p.id = al.person_id
        """
    )
    stored = list(cur.fetchall())
    sheets_by_file: dict[str, dict[str, list[list]] | None] = {}
    counts = {
        "lines": len(stored),
        "items": 0,
        "sources": 0,
        "aps": 0,
        "service": 0,
        "titular": 0,
        "duplicates": 0,
        "files_missing": 0,
        "file_errors": 0,
    }
    parsed: dict[str, dict] = {}
    copies: list[RequestCopy] = []

    for row in stored:
        source_file = row["source_file"] or ""
        workbook = sheets_by_file.get(source_file, "miss")
        if workbook == "miss":
            path = Path(source_file) if Path(source_file).is_absolute() else BACKUP / source_file
            if not path.is_file():
                sheets_by_file[source_file] = None
                counts["files_missing"] += 1
                workbook = None
            else:
                try:
                    workbook = _load_sheets(path)
                except Exception:  # noqa: BLE001
                    counts["file_errors"] += 1
                    workbook = None
                sheets_by_file[source_file] = workbook
        items, titular_ci = _items_for(workbook or {}, row["source_row"] or "", row["service_description"])
        patient_ci = _digits(row["identity_number"])
        titular_id = None
        if titular_ci and titular_ci != patient_ci:
            other = people.get(titular_ci)
            if other and other != row["person_id"]:
                titular_id = other
        copy = RequestCopy(
            line_id=row["id"],
            person_id=row["person_id"],
            source_file=source_file,
            source_row=row["source_row"] or "",
            source_hash=row["source_hash"],
            service_date=row["service_date"],
            amount_bs=row["amount_bs"],
            diagnosis=row["diagnosis"],
            labels=tuple(item.label for item in items),
            invoice_id=row["invoice_id"],
            referenced=bool(row["invoice_id"]) or row["id"] in reviewed,
        )
        parsed[row["id"]] = {"row": row, "items": items, "titular_id": titular_id, "copy": copy}
        copies.append(copy)

    extras_of: dict[str, str] = {}
    for canonical, extras in partition_copies(copies):
        for extra in extras:
            extras_of[extra.line_id] = canonical.line_id

    def remember_source(line_id: str, source_file: str, source_row: str, source_hash: str, reason: str) -> None:
        if not source_hash or not source_file or not source_row:
            return
        if source_hash in have_hashes:
            return
        have_hashes.add(source_hash)
        counts["sources"] += 1
        if not apply:
            return
        cur.execute(
            """
            INSERT INTO avila.authorization_source (
              authorization_line_id, source_file, source_row, source_hash
            ) VALUES (%s::uuid, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT authorization_source_hash DO NOTHING
            RETURNING id::text
            """,
            (line_id, source_file, source_row, source_hash),
        )
        inserted = cur.fetchone()
        if not inserted:
            counts["sources"] -= 1
            return
        with provenance.source("workbook", source_ref(source_file, source_row)):
            provenance.record(
                cur,
                entity="authorization_source",
                entity_id=inserted["id"],
                field="source_hash",
                old=None,
                new=source_hash,
                rule_id="authorization_source",
                reason=reason,
            )

    def fill_text(row: dict, field: str, value: str | None, rule_id: str, reason: str, counter: str) -> None:
        if field not in {"aps_code", "service_description"} or not value:
            return
        current = row.get(field)
        if current is not None and str(current).strip():
            return
        counts[counter] += 1
        if not apply:
            return
        if field == "aps_code":
            cur.execute(
                """
                UPDATE avila.authorization_line
                SET aps_code = %s
                WHERE id = %s::uuid
                  AND (aps_code IS NULL OR btrim(aps_code) = '')
                RETURNING id::text
                """,
                (value, row["id"]),
            )
        else:
            cur.execute(
                """
                UPDATE avila.authorization_line
                SET service_description = %s
                WHERE id = %s::uuid
                  AND (service_description IS NULL OR btrim(service_description) = '')
                RETURNING id::text
                """,
                (value, row["id"]),
            )
        if not cur.fetchone():
            counts[counter] -= 1
            return
        with provenance.source("workbook", source_ref(row["source_file"] or "", row["source_row"] or "")):
            provenance.record(
                cur,
                entity="authorization_line",
                entity_id=row["id"],
                field=field,
                old=None,
                new=value,
                rule_id=rule_id,
                reason=reason,
            )

    for line_id, item in parsed.items():
        row = item["row"]
        canonical_id = extras_of.get(line_id)
        if canonical_id:
            remember_source(canonical_id, row["source_file"] or "", row["source_row"] or "", row["source_hash"], "duplicate_copy")
        else:
            remember_source(line_id, row["source_file"] or "", row["source_row"] or "", row["source_hash"], "workbook_row")
            for auth_item in item["items"]:
                key = (line_id, auth_item.source_row)
                if key in have_items:
                    continue
                have_items.add(key)
                counts["items"] += 1
                if not apply:
                    continue
                cur.execute(
                    """
                    INSERT INTO avila.authorization_item (
                      authorization_line_id, position, kind, label, quantity, source_row
                    ) VALUES (%s::uuid, %s, %s, %s, %s, %s)
                    ON CONFLICT ON CONSTRAINT authorization_item_line_row DO NOTHING
                    RETURNING id::text
                    """,
                    (
                        line_id,
                        auth_item.position,
                        auth_item.kind,
                        auth_item.label,
                        auth_item.quantity,
                        auth_item.source_row,
                    ),
                )
                inserted = cur.fetchone()
                if not inserted:
                    counts["items"] -= 1
                    continue
                with provenance.source("workbook", source_ref(row["source_file"] or "", row["source_row"] or "")):
                    provenance.record(
                        cur,
                        entity="authorization_item",
                        entity_id=inserted["id"],
                        field="label",
                        old=None,
                        new=auth_item.label,
                        rule_id="authorization_item",
                        reason=auth_item.reason,
                    )
        fill_text(
            row,
            "aps_code",
            aps_code_from_path(row["source_file"]),
            "authorization_aps_code",
            "aps_in_filename",
            "aps",
        )
        first = item["items"][0].label if item["items"] else None
        fill_text(row, "service_description", first, "authorization_service_label", "first_item", "service")
        titular_id = item["titular_id"]
        if titular_id and not row["titular_person_id"]:
            counts["titular"] += 1
            if apply:
                cur.execute(
                    """
                    UPDATE avila.authorization_line
                    SET titular_person_id = %s::uuid
                    WHERE id = %s::uuid
                      AND titular_person_id IS NULL
                      AND person_id IS DISTINCT FROM %s::uuid
                    RETURNING id::text
                    """,
                    (titular_id, line_id, titular_id),
                )
                if not cur.fetchone():
                    counts["titular"] -= 1
                else:
                    with provenance.source("workbook", source_ref(row["source_file"] or "", row["source_row"] or "")):
                        provenance.record(
                            cur,
                            entity="authorization_line",
                            entity_id=line_id,
                            field="titular_person_id",
                            old=None,
                            new=titular_id,
                            rule_id="authorization_titular",
                            reason="titular_ci_on_sheet",
                        )
        if not canonical_id:
            continue
        if row["duplicate_of"] or row["invoice_id"] or line_id in reviewed:
            continue
        counts["duplicates"] += 1
        if not apply:
            continue
        cur.execute(
            """
            UPDATE avila.authorization_line
            SET duplicate_of = %s::uuid
            WHERE id = %s::uuid
              AND duplicate_of IS NULL
              AND invoice_id IS NULL
              AND id <> %s::uuid
              AND NOT EXISTS (
                SELECT 1 FROM avila.review_item r
                WHERE r.authorization_line_id = avila.authorization_line.id
              )
            RETURNING id::text
            """,
            (canonical_id, line_id, canonical_id),
        )
        if not cur.fetchone():
            counts["duplicates"] -= 1
            continue
        with provenance.source("workbook", source_ref(row["source_file"] or "", row["source_row"] or "")):
            provenance.record(
                cur,
                entity="authorization_line",
                entity_id=line_id,
                field="duplicate_of",
                old=None,
                new=canonical_id,
                rule_id="authorization_duplicate",
                reason="same_request_copy",
            )
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Normalize authorization items and sources")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    url = database_url()
    provenance.start_run(url, "repair_authorization_items", {"apply": args.apply}, apply=args.apply)
    conn = connect()
    counts: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            counts = repair(cur, args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"apply_failed=1 error={type(exc).__name__}")
        raise
    finally:
        conn.close()
        provenance.finish_run(url, counts)
    print(
        "lines={lines} items={items} sources={sources} aps={aps} service={service} "
        "titular={titular} duplicates={duplicates} files_missing={files_missing} "
        "file_errors={file_errors} apply={apply}".format(**counts, apply=1 if args.apply else 0)
    )


if __name__ == "__main__":
    main()
