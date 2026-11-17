#!/usr/bin/env python3
"""Read structured fields from fiscal sheet (forma libre) OCR.

Fields: invoice number, control number, issue date, titular name + CI, patient
name + CI, ORDEN / CLAVE, service line descriptions, totals (Bs, USD).

The CLI fills ``control_number``, ``issue_date``, ``total_bs``, ``total_usd`` and
``clave`` on ``avila.invoice`` (fill-only, with provenance) and writes the full
extract to ``output/invoices/fiscal-extract.jsonl`` (git-ignored) for the
authorization-line matcher. ``--link-roles`` also links the titular and patient
through ``try_promote_ci_titular`` with source ``fiscal_ocr``.

  PYTHONPATH=scripts .venv/bin/python scripts/fiscal_extract.py              # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/fiscal_extract.py --apply [--link-roles]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from invoice_rules import fold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_JSONL = ROOT / "output" / "invoices" / "fiscal-extract.jsonl"

_CONTROL_LABEL = re.compile(r"D\s*E?\s*CONTROL")
_INVOICE_NO = re.compile(
    r"FACTURA\s*N[O0°º*?]?\W{0,3}\s*(?:DE\s+)?(\d{3,10})\b|N\W{0,2}\s*(?:RO\.?\s*)?DE\s+FACTURA\W{0,3}(\d{3,10})\b"
)
_DATE = r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})"
_ISSUE_DATE = re.compile(rf"FECHA\s+DE\s+EMISI[O0]N\W{{0,4}}{_DATE}")
_ANY_DATE = re.compile(rf"\bFECHA\b\W{{0,4}}{_DATE}")
_NAME = r"([A-Z][A-Z .'\-]{2,60}?)"
_CI = r"(?:(?:[VE]\s*-?\s*)|(?:C\.?\s*I\.?\W{0,3}[VE]?\s*-?\s*))(\d{1,2}\.?\d{3}\.?\d{3}|\d{6,9})\b"
_TITULAR = re.compile(rf"TITULAR\s*:?\s*{_NAME}\s*(?:{_CI})?\s*$", re.M)
_PACIENTE = re.compile(rf"PACIENTE\s*:?\s*{_NAME}\s*(?:{_CI})?\s*$", re.M)
_CLAVE = re.compile(
    r"\b(?:ORDEN|CLAVE(?:\s+RMS)?|N\W?\s*AUTORIZACI[O0]N|AUTORIZACI[O0]N)\s*(?:N\W{0,2})?\s*:?\s*([A-Z0-9][A-Z0-9\-]{3,20})"
)
_AMOUNT = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
_TOTAL = re.compile(rf"TOTAL\s+(?:FACTURA|A\s+PAGAR)\s*:?\s*{_AMOUNT}(?:\s+{_AMOUNT})?")
_SERVICE_START = re.compile(r"FACTURACION|DESCRIPCION|CONCEPTO|PACIENTE")
_SERVICE_END = re.compile(r"TOTAL\s+SERVICIOS|MONTO\s+BRUTO|SUB\s*-?\s*TOTAL|BASE\s+IMPONIBLE|TOTAL\s+FACTURA")
_SERVICE_LINE = re.compile(rf"^\W*([A-Z][A-Z ./\-]{{3,60}}?)\s*(?:\(|\d).*{_AMOUNT}")


@dataclass
class FiscalFields:
    invoice_number: str | None = None
    control_number: str | None = None
    issue_date: dt.date | None = None
    titular_name: str | None = None
    titular_ci: str | None = None
    patient_name: str | None = None
    patient_ci: str | None = None
    clave: str | None = None
    total_bs: float | None = None
    total_usd: float | None = None
    services: list[str] = field(default_factory=list)

    def merge(self, other: "FiscalFields") -> None:
        for key, value in asdict(other).items():
            if key == "services":
                self.services.extend(s for s in other.services if s not in self.services)
            elif getattr(self, key) in (None, "") and value not in (None, ""):
                setattr(self, key, value)


def _amount(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _date(d: str, m: str, y: str) -> dt.date | None:
    year = int(y)
    if year < 100:
        year += 2000
    try:
        value = dt.date(year, int(m), int(d))
    except ValueError:
        return None
    return value if 2015 <= value.year <= 2035 else None


def _clean_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = re.sub(r"\s+", " ", re.sub(r"[^A-Z .'\-]", " ", raw)).strip(" .-'")
    name = re.sub(r"\b(?:C\.?\s*I|RIF|V|E)\.?$", "", name).strip(" .-")
    return name if len(name.split()) >= 2 else None


def norm_control(value: str | None) -> str | None:
    """Canonical ``SS-NNNNNN``: OCR drops or mangles the two-digit series, which is 00 here."""
    if not value:
        return None
    runs = re.findall(r"\d+", value)
    if not runs:
        return None
    series = runs[0] if len(runs) > 1 and len(runs[0]) <= 2 else "00"
    body = "".join(runs[1:] if series == runs[0] and len(runs) > 1 else runs)
    if not 4 <= len(body) <= 8:
        return None
    return f"{int(series):02d}-{int(body):06d}"


def _control(folded: str) -> str | None:
    """Number printed after N° DE CONTROL (series may be noise: "(0... 012967", "00 — 5114 73")."""
    for m in _CONTROL_LABEL.finditer(folded):
        window = folded[m.end() : m.end() + 24].split("\n")[0]
        runs = re.findall(r"\d+", window)
        if not runs:
            continue
        body_runs = [r for r in runs if len(r) >= 3]
        if not body_runs:
            continue
        start = runs.index(body_runs[0])
        body = body_runs[0]
        if len(body) < 6 and start + 1 < len(runs) and len(body + runs[start + 1]) <= 8:
            body += runs[start + 1]
        series = runs[start - 1] if start > 0 and len(runs[start - 1]) <= 2 else "00"
        found = norm_control(f"{series}-{body}")
        if found:
            return found
    return None


def _ci(raw: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    return digits if 6 <= len(digits) <= 9 else None


def extract(text: str | None) -> FiscalFields:
    out = FiscalFields()
    if not text:
        return out
    folded = fold(text)
    out.control_number = _control(folded)
    if m := _INVOICE_NO.search(folded):
        out.invoice_number = str(int(m.group(1) or m.group(2)))
    if m := (_ISSUE_DATE.search(folded) or _ANY_DATE.search(folded)):
        out.issue_date = _date(*m.groups())
    if m := _TITULAR.search(folded):
        out.titular_name, out.titular_ci = _clean_name(m.group(1)), _ci(m.group(2))
    if m := _PACIENTE.search(folded):
        out.patient_name, out.patient_ci = _clean_name(m.group(1)), _ci(m.group(2))
    if m := _CLAVE.search(folded):
        value = m.group(1).strip("-")
        if re.search(r"\d{4,}", value):
            out.clave = value
    if m := _TOTAL.search(folded):
        out.total_bs, out.total_usd = _amount(m.group(1)), _amount(m.group(2))
    out.services = service_lines(folded)
    return out


def service_lines(folded: str) -> list[str]:
    lines = folded.splitlines()
    start = next((i for i, line in enumerate(lines) if _SERVICE_START.search(line)), None)
    if start is None:
        return []
    found: list[str] = []
    for line in lines[start + 1 :]:
        if _SERVICE_END.search(line):
            break
        if m := _SERVICE_LINE.search(line):
            desc = re.sub(r"\s+", " ", m.group(1)).strip(" .-")
            if len(desc) >= 4 and desc not in found:
                found.append(desc)
    return found[:20]


# --- CLI -------------------------------------------------------------------


def _fiscal_pages(cur) -> dict[str, list[dict]]:
    cur.execute(
        """
        SELECT d.invoice_id::text AS invoice_id, i.invoice_number, d.page_index, sf.backup_path
        FROM avila.document d
        JOIN avila.invoice i ON i.id = d.invoice_id
        JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.document_type = 'factura_fiscal' AND d.page_index < 900
        ORDER BY d.invoice_id, sf.backup_path, d.page_index
        """
    )
    pages: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        pages.setdefault(row["invoice_id"], []).append(row)
    return pages


INVOICE_FIELDS = ("control_number", "issue_date", "total_bs", "total_usd", "clave")


def invoice_number_agrees(stored: str, extracted: str | None) -> bool:
    """False only when OCR clearly read a different invoice number.

    Short fragments are OCR noise, and a printed series prefix (``2000`` + number)
    still names the same invoice.
    """
    if not extracted:
        return True
    want = str(int(stored))
    got = extracted.lstrip("0")
    if len(got) < len(want):
        return True
    return got == want or (got.endswith(want) and len(got) - len(want) <= 4)


def _invoice_fields(cur) -> dict[str, dict]:
    cur.execute(f"SELECT id::text AS id, {', '.join(INVOICE_FIELDS)} FROM avila.invoice")
    return {r["id"]: r for r in cur.fetchall()}


def write_invoice_fields(
    cur, invoice_id: str, fields: FiscalFields, stats: Counter, before: dict | None = None
) -> None:
    import provenance

    if before is None:
        cur.execute(
            f"SELECT {', '.join(INVOICE_FIELDS)} FROM avila.invoice WHERE id = %s", (invoice_id,)
        )
        before = cur.fetchone()
    updates = {}
    for name in INVOICE_FIELDS:
        new = getattr(fields, name)
        if new in (None, ""):
            continue
        old = before[name]
        if old in (None, ""):
            updates[name] = new
        elif provenance.value_hash(old) != provenance.value_hash(new):
            stats[f"conflict:{name}"] += 1
    if updates:
        sets = ", ".join(f"{k} = %s" for k in updates)
        cur.execute(
            f"UPDATE avila.invoice SET {sets}, fiscal_extracted_at = now() WHERE id = %s",
            (*updates.values(), invoice_id),
        )
        for name, new in updates.items():
            provenance.record(
                cur, entity="invoice", entity_id=invoice_id, field=name,
                old=None, new=new, rule_id="fiscal_extract",
            )
            stats[f"set:{name}"] += 1
    else:
        cur.execute("UPDATE avila.invoice SET fiscal_extracted_at = now() WHERE id = %s", (invoice_id,))


def link_fiscal_roles(cur, invoice_id: str, fields: FiscalFields, stats: Counter) -> None:
    from person_upsert import upsert_by_ci, upsert_by_name
    from upload_documents_to_blob import link_invoice_person, try_promote_ci_titular

    titular_id = None
    if fields.titular_ci:
        titular_id, _ = upsert_by_ci(cur, identity_number=fields.titular_ci, full_name=fields.titular_name)
        outcome = try_promote_ci_titular(cur, invoice_id, titular_id, source="fiscal_ocr")
        stats[f"titular:{outcome}"] += 1
    patient_is_titular = bool(
        fields.patient_ci and fields.patient_ci == fields.titular_ci
    ) or bool(fields.patient_name and fields.patient_name == fields.titular_name)
    if patient_is_titular or not fields.patient_name:
        return
    if fields.patient_ci and fields.patient_ci != fields.titular_ci:
        patient_id, _ = upsert_by_ci(cur, identity_number=fields.patient_ci, full_name=fields.patient_name)
    else:
        patient_id, _ = upsert_by_name(cur, full_name=fields.patient_name)
    if patient_id and patient_id != titular_id:
        link_invoice_person(
            cur, invoice_id, patient_id, "beneficiario", source="fiscal_ocr", rule_id="fiscal_patient"
        )
        stats["patient_linked"] += 1


def _extract_invoice(cur, invoice_id: str, rows: list[dict], before, args, stats: Counter, out) -> None:
    import provenance
    from ocr_invoice_pages import _read_cache

    stats["invoices"] += 1
    fields = FiscalFields()
    for row in rows:
        cache = _read_cache(row["backup_path"])
        if not cache:
            continue
        page_records = cache.get("pages") or []
        idx = int(row["page_index"]) - 1
        if 0 <= idx < len(page_records):
            fields.merge(extract(page_records[idx].get("text") or ""))
    number = rows[0]["invoice_number"]
    if not number.isdigit():
        stats["skipped_synthetic_invoice"] += 1
        return
    if not invoice_number_agrees(number, fields.invoice_number):
        stats["number_mismatch"] += 1
        return
    for name in ("control_number", "issue_date", "titular_ci", "patient_name", "clave", "total_bs"):
        if getattr(fields, name):
            stats[f"has:{name}"] += 1
    out.write(json.dumps({"invoice_id": invoice_id, **asdict(fields)}, default=str, ensure_ascii=False) + "\n")
    with provenance.source("ocr", f"{rows[0]['backup_path']}#{rows[0]['page_index']}"):
        write_invoice_fields(cur, invoice_id, fields, stats, before)
        if args.link_roles:
            link_fiscal_roles(cur, invoice_id, fields, stats)


def main() -> int:
    import psycopg
    from psycopg.rows import dict_row

    import provenance
    from env_load import load_env

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--link-roles", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, "fiscal_extract", vars(args), apply=args.apply)
    stats: Counter = Counter()
    EXTRACT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur, EXTRACT_JSONL.open(
        "w", encoding="utf-8"
    ) as out:
        pages = _fiscal_pages(cur)
        current = _invoice_fields(cur)
        items = list(pages.items())[: args.limit or None]
        with conn.pipeline():
            for invoice_id, rows in items:
                _extract_invoice(cur, invoice_id, rows, current.get(invoice_id), args, stats, out)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run", dict(sorted(stats.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
