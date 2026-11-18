#!/usr/bin/env python3
"""Fill empty birth date, phone, and address from Avila-backup page text.

Reads the OCR cache for loaded documents and for scanner packets at confidence
>= 0.6 that resolve to an invoice. Workbook values are left to
repair_workbook_contact.py, which should run first. Dry-run by default.

Every person gets a contact_gap code per field. Counts go to output/runs.
Per-person evidence (hashes, no raw values) goes to
output/persons/_queue/contact-gaps.jsonl.

  PYTHONPATH=scripts .venv/bin/python scripts/enrich_person_contact.py
  PYTHONPATH=scripts .venv/bin/python scripts/enrich_person_contact.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from contact_extract import (  # noqa: E402
    FORM_TYPES,
    ID_TYPES,
    Candidate,
    PersonOnInvoice,
    bind_candidate,
    extract_page,
    is_minor_beneficiario,
    names_compatible,
    address_signature,
    repeated_address_signatures,
    same_value,
    select_address_hits,
)
from document_types import classify_document  # noqa: E402
from ocr_invoice_pages import cache_path  # noqa: E402
from titular_queue import is_junk_titular  # noqa: E402
from workbook_enrichment.db import connect, database_url  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT / "output" / "invoices" / "scan-packets.csv"
GAPS = ROOT / "output" / "persons" / "_queue" / "contact-gaps.jsonl"
LOW_CONFIDENCE = 0.6

FIELD_TYPES = {
    "birth_date": ID_TYPES | {"acta_nacimiento", "informe_medico", "comprobante"},
    "phone": set(FORM_TYPES),
    "address": set(FORM_TYPES) | {"acta_nacimiento"},
}
SKIP_TYPES = {"ilegible", "factura_fiscal"}


@dataclass
class Hit:
    value: object
    confidence: float
    rule_id: str
    ref: str


def _norm_invoice(value: str | None) -> str:
    text = (value or "").strip()
    if text.isdigit():
        return str(int(text))
    return ""


def _norm_control(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _page_text(payload: dict | None, page_index: int) -> str:
    if not payload:
        return ""
    pages = payload.get("pages") or []
    for page in pages:
        if isinstance(page, dict) and int(page.get("page") or 0) == page_index:
            return page.get("text") or ""
    if 1 <= page_index <= len(pages) and isinstance(pages[page_index - 1], dict):
        return pages[page_index - 1].get("text") or ""
    return ""


def _load_ocr(relative: str) -> dict | None:
    path = cache_path(relative)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cluster(field_name: str, hits: list[Hit]) -> list[list[Hit]]:
    groups: list[list[Hit]] = []
    for hit in hits:
        placed = False
        for group in groups:
            if same_value(field_name, group[0].value, hit.value):
                group.append(hit)
                placed = True
                break
        if not placed:
            groups.append([hit])
    return groups


def _best(field_name: str, group: list[Hit]) -> Hit:
    if field_name == "address":
        return max(group, key=lambda hit: (len(str(hit.value)), hit.confidence))
    return max(group, key=lambda hit: hit.confidence)


def _pick(field_name: str, hits: list[Hit], stored: object) -> tuple[str, Hit | None, object | None]:
    """Return action, chosen hit, and an alternate phone value.

    Actions: fill, keep, conflict. fill is only when the stored value is empty.
    """
    if field_name == "address":
        selected = select_address_hits(hits, stored)
        if selected is None:
            return "keep", None, None
        hits = selected
    groups = _cluster(field_name, hits)
    if not groups:
        return "keep", None, None
    groups.sort(key=lambda group: max(hit.confidence for hit in group), reverse=True)
    if len(groups) > 1 and field_name == "phone":
        top = max(hit.confidence for hit in groups[0])
        second = max(hit.confidence for hit in groups[1])
        if top >= second + 0.15:
            chosen = _best(field_name, groups[0])
            alternate = _best(field_name, groups[1]).value
            if not stored or same_value(field_name, stored, chosen.value):
                return "fill" if not stored else "keep", chosen, alternate
            return "conflict", None, None
    if len(groups) > 1:
        return "conflict", None, None
    chosen = _best(field_name, groups[0])
    if not stored:
        return "fill", chosen, None
    if same_value(field_name, stored, chosen.value):
        return "keep", chosen, None
    return "conflict", None, None


def _gap_code(field_name: str, *, has_value: bool, conflict: bool, junk: bool, minor: bool, flags: set[str], relevant: int, has_invoice: bool, cached: bool, uncached: bool, low_conf: bool) -> str:
    if conflict:
        return "conflict"
    if has_value:
        return "filled"
    if junk:
        return "junk"
    if "blocked" in flags:
        return "blocked_review"
    if "ambiguous" in flags:
        return "ambiguous"
    if "letterhead" in flags:
        return "only_letterhead"
    if "unparsed" in flags:
        return "unparsed"
    if minor and field_name in {"phone", "address"}:
        return "not_applicable_menor"
    if low_conf and relevant == 0:
        return "unsegmented_scan"
    if relevant:
        return "ocr_no_cue"
    if uncached and not cached:
        return "outside_ocr_scope"
    if not has_invoice:
        return "no_invoice_documents"
    return "no_candidate_page"


def _append_note(existing: str | None, number: object) -> str:
    line = f"Tel. alterno: {number}"
    text = (existing or "").strip()
    if line in text:
        return text
    return f"{text}\n{line}".strip()


def _hint_role(person_id: str | None, people: list[PersonOnInvoice]) -> str | None:
    if not person_id:
        return None
    roles = [person.role for person in people if person.person_id == person_id]
    if "beneficiario" in roles:
        return "beneficiario"
    if "titular" in roles:
        return "titular"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = database_url()
    provenance.start_run(url, "enrich_person_contact", {"apply": args.apply}, apply=args.apply)
    stats: Counter = Counter()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id, full_name, identity_number,
                       birth_date, phone, address, notes
                FROM avila.person
                """
            )
            persons = {row["id"]: dict(row) for row in cur.fetchall()}
            cur.execute(
                """
                SELECT person_id::text AS person_id, invoice_id::text AS invoice_id,
                       role::text AS role, parentesco
                FROM avila.invoice_person
                """
            )
            roles = cur.fetchall()
            cur.execute(
                """
                SELECT id::text AS id, invoice_number, control_number
                FROM avila.invoice
                """
            )
            invoices = cur.fetchall()
            cur.execute(
                """
                SELECT invoice_id::text AS invoice_id
                FROM avila.review_item
                WHERE status = 'open'
                  AND kind IN ('multiple_ci', 'ci_conflict')
                  AND invoice_id IS NOT NULL
                """
            )
            blocked = {row["invoice_id"] for row in cur.fetchall()}
            cur.execute(
                """
                SELECT d.page_index, d.document_type::text AS document_type,
                       d.person_id::text AS person_id, d.invoice_id::text AS invoice_id,
                       sf.backup_path
                FROM avila.document d
                JOIN avila.source_file sf ON sf.id = d.source_file_id
                WHERE d.document_type::text NOT IN ('ilegible', 'factura_fiscal')
                """
            )
            documents = cur.fetchall()

        by_invoice: dict[str, list[PersonOnInvoice]] = defaultdict(list)
        role_rows: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for row in roles:
            person = persons.get(row["person_id"])
            if not person:
                continue
            by_invoice[row["invoice_id"]].append(
                PersonOnInvoice(
                    row["person_id"],
                    person.get("full_name"),
                    person.get("identity_number"),
                    row["role"],
                    row.get("parentesco"),
                )
            )
            role_rows[row["person_id"]].append((row["role"], row.get("parentesco")))

        by_ci: dict[str, str] = {}
        ci_dupes: set[str] = set()
        for person_id, person in persons.items():
            number = person.get("identity_number")
            if not number:
                continue
            if number in by_ci and by_ci[number] != person_id:
                ci_dupes.add(number)
            else:
                by_ci[number] = person_id
        for number in ci_dupes:
            by_ci.pop(number, None)

        by_number: dict[str, str] = {}
        number_dupes: set[str] = set()
        by_control: dict[str, str] = {}
        control_dupes: set[str] = set()
        for row in invoices:
            key = _norm_invoice(row.get("invoice_number"))
            if key:
                if key in by_number and by_number[key] != row["id"]:
                    number_dupes.add(key)
                else:
                    by_number[key] = row["id"]
            control = _norm_control(row.get("control_number"))
            if control:
                if control in by_control and by_control[control] != row["id"]:
                    control_dupes.add(control)
                else:
                    by_control[control] = row["id"]
        for key in number_dupes:
            by_number.pop(key, None)
        for key in control_dupes:
            by_control.pop(key, None)

        hits: dict[str, dict[str, list[Hit]]] = defaultdict(lambda: defaultdict(list))
        flags: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        relevant: dict[str, Counter] = defaultdict(Counter)
        meta = {
            pid: {"has_invoice": bool(role_rows.get(pid)), "cached": False, "uncached": False, "low_conf": False}
            for pid in persons
        }
        phone_invoices: dict[str, set[str]] = defaultdict(set)
        phone_titulares: dict[str, set[str]] = defaultdict(set)
        address_records: list[tuple[str, str, str]] = []
        seen_pages: set[tuple[str, int]] = set()

        def consider(
            relative: str,
            page_index: int,
            document_type: str,
            invoice_id: str | None,
            hint_person_id: str | None,
            text: str,
            cached: bool,
        ) -> None:
            if (relative, page_index) in seen_pages:
                return
            seen_pages.add((relative, page_index))
            people = by_invoice.get(invoice_id or "", [])
            for person in people:
                slot = meta[person.person_id]
                slot["cached" if cached else "uncached"] = True
            if document_type in SKIP_TYPES or not text.strip():
                return
            extracted = extract_page(text, document_type)
            sole_dob = sum(1 for candidate in extracted.candidates if candidate.field == "birth_date") == 1
            hint_role = _hint_role(hint_person_id, people)
            for person in people:
                for field_name, types in FIELD_TYPES.items():
                    if document_type in types:
                        relevant[person.person_id][field_name] += 1
                for field_name in ("birth_date", "phone", "address"):
                    if field_name in extracted.cues and not any(c.field == field_name for c in extracted.candidates):
                        flags[person.person_id][field_name].add("unparsed")
                for field_name in extracted.letterhead_fields:
                    flags[person.person_id][field_name].add("letterhead")
            ref = f"{relative}#{page_index}"
            titulares = [person.person_id for person in people if person.role == "titular"]
            for candidate in extracted.candidates:
                person_id, status = bind_candidate(
                    candidate,
                    people,
                    blocked=bool(invoice_id and invoice_id in blocked),
                    persons_by_ci=by_ci,
                    hint_person_id=hint_person_id,
                    hint_role=hint_role,
                    sole_dob=sole_dob,
                )
                if status == "bound" and person_id:
                    hits[person_id][candidate.field].append(
                        Hit(candidate.value, candidate.confidence, candidate.rule_id, ref)
                    )
                    if candidate.field == "phone":
                        bucket = invoice_id or relative
                        phone_invoices[str(candidate.value)].add(bucket)
                        for titular_id in titulares:
                            phone_titulares[str(candidate.value)].add(titular_id)
                    elif candidate.field == "address":
                        for titular_id in titulares:
                            address_records.append(
                                (str(candidate.value), invoice_id or relative, titular_id)
                            )
                    stats["bound"] += 1
                elif status == "ambiguous":
                    _mark_ambiguous(candidate, people, flags)
                    stats["ambiguous"] += 1
                elif status == "blocked_review":
                    for person in people:
                        flags[person.person_id][candidate.field].add("blocked")
                    stats["blocked"] += 1

        grouped: dict[str, list] = defaultdict(list)
        for doc in documents:
            grouped[doc["backup_path"]].append(doc)
        for index, (relative, pages) in enumerate(grouped.items(), start=1):
            payload = _load_ocr(relative)
            for doc in pages:
                page_index = int(doc["page_index"])
                consider(
                    relative,
                    page_index,
                    doc["document_type"],
                    doc.get("invoice_id"),
                    doc.get("person_id"),
                    _page_text(payload, page_index),
                    payload is not None,
                )
            if index % 5000 == 0:
                stats["ocr_files"] = index
        stats["document_pages"] = len(seen_pages)

        if PACKETS.is_file():
            with PACKETS.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    confidence = float(row.get("confidence") or 0)
                    invoice_id = by_number.get(_norm_invoice(row.get("invoice_number"))) or by_control.get(
                        _norm_control(row.get("control_number"))
                    )
                    refs = [part for part in (row.get("page_refs") or "").split("|") if part]
                    types = (row.get("page_types") or "").split("|")
                    if confidence < LOW_CONFIDENCE:
                        stats["scanner_low"] += 1
                        if invoice_id:
                            for person in by_invoice.get(invoice_id, []):
                                meta[person.person_id]["low_conf"] = True
                        continue
                    if not invoice_id:
                        stats["scanner_unmatched"] += 1
                        continue
                    stats["scanner_packets"] += 1
                    packet_cache: dict[str, dict | None] = {}
                    for index, ref in enumerate(refs):
                        if "#" not in ref:
                            continue
                        relative, page_s = ref.rsplit("#", 1)
                        try:
                            page_index = int(page_s)
                        except ValueError:
                            continue
                        if relative not in packet_cache:
                            packet_cache[relative] = _load_ocr(relative)
                        payload = packet_cache[relative]
                        text = _page_text(payload, page_index)
                        document_type = types[index] if index < len(types) and types[index] else ""
                        if not document_type:
                            document_type, _evidence = classify_document(text, backup_path=relative)
                        consider(
                            relative,
                            page_index,
                            document_type,
                            invoice_id,
                            None,
                            text,
                            payload is not None,
                        )

        denied = {
            number
            for number, invoices_seen in phone_invoices.items()
            if len(invoices_seen) >= 8 and len(phone_titulares[number]) >= 3
        }
        denied_addresses = repeated_address_signatures(address_records)
        stats["letterhead_addresses"] = len(denied_addresses)
        stats["letterhead_numbers"] = len(denied)
        for person_id, fields in hits.items():
            phones = fields.get("phone") or []
            kept = [hit for hit in phones if str(hit.value) not in denied]
            if len(kept) != len(phones):
                flags[person_id]["phone"].add("letterhead")
            fields["phone"] = kept
            addresses = fields.get("address") or []
            kept_addresses = [
                hit for hit in addresses if address_signature(str(hit.value)) not in denied_addresses
            ]
            if len(kept_addresses) != len(addresses):
                flags[person_id]["address"].add("letterhead")
            fields["address"] = kept_addresses

        ledger: list[dict] = []
        updates: list[dict] = []
        writes: list[tuple] = []
        reviews: list[tuple] = []
        for person_id, person in persons.items():
            junk = is_junk_titular(person)
            chosen_birth = person.get("birth_date")
            gap: dict[str, str] = {}
            new_values: dict[str, object] = {"birth_date": None, "phone": None, "address": None, "notes": None}
            for field_name in ("birth_date", "phone", "address"):
                stored = person.get(field_name)
                action, hit, alternate = _pick(field_name, hits.get(person_id, {}).get(field_name, []), stored)
                if junk and action == "fill":
                    action, hit, alternate = "keep", None, None
                    stats["skipped_junk"] += 1
                conflict = action == "conflict"
                if action == "fill" and hit is not None:
                    new_values[field_name] = hit.value
                    stored = hit.value
                    stats[f"filled:{field_name}"] += 1
                    stats[f"filled_rule:{hit.rule_id}"] += 1
                    writes.append((person_id, field_name, hit))
                    if field_name == "birth_date":
                        chosen_birth = hit.value
                    if alternate and field_name == "phone":
                        notes = _append_note(person.get("notes"), alternate)
                        if notes != (person.get("notes") or "").strip():
                            new_values["notes"] = notes
                            writes.append((person_id, "notes", Hit(notes, 0.6, "informe_phone_alt", hit.ref)))
                            stats["phone_alternate"] += 1
                if conflict:
                    stats[f"conflict:{field_name}"] += 1
                    kind = {"birth_date": "dob_conflict", "phone": "phone_conflict", "address": "address_conflict"}[field_name]
                    reviews.append((kind, person_id, field_name))
                minor = _is_minor(role_rows.get(person_id, []), chosen_birth)
                slot = meta[person_id]
                code = _gap_code(
                    field_name,
                    has_value=bool(stored),
                    conflict=conflict,
                    junk=junk,
                    minor=minor,
                    flags=flags[person_id][field_name],
                    relevant=relevant[person_id][field_name],
                    has_invoice=slot["has_invoice"],
                    cached=slot["cached"],
                    uncached=slot["uncached"],
                    low_conf=slot["low_conf"],
                )
                gap[field_name] = code
                stats[f"gap:{field_name}:{code}"] += 1
                ledger.append(
                    {
                        "person_id": person_id,
                        "field": field_name,
                        "code": code,
                        "rule_id": hit.rule_id if hit else None,
                        "source_ref": hit.ref if hit else None,
                        "value_hash": provenance.value_hash(stored) if stored else None,
                    }
                )
            updates.append(
                {
                    "id": person_id,
                    "birth_date": new_values["birth_date"].isoformat() if hasattr(new_values["birth_date"], "isoformat") else new_values["birth_date"],
                    "phone": new_values["phone"],
                    "address": new_values["address"],
                    "notes": new_values["notes"],
                    "contact_gap": gap,
                }
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE avila.person AS p SET
                  birth_date = COALESCE(p.birth_date, v.birth_date),
                  phone = COALESCE(NULLIF(p.phone, ''), v.phone),
                  address = COALESCE(NULLIF(p.address, ''), v.address),
                  notes = COALESCE(v.notes, p.notes),
                  contact_gap = v.contact_gap,
                  updated_at = now()
                FROM jsonb_to_recordset(%s::jsonb) AS v(
                  id uuid, birth_date date, phone text, address text, notes text, contact_gap jsonb
                )
                WHERE p.id = v.id
                """,
                (json.dumps(updates),),
            )
            with conn.pipeline():
                for person_id, field_name, hit in writes:
                    with provenance.source("ocr", hit.ref):
                        old = None if field_name != "notes" else persons[person_id].get("notes")
                        provenance.record(
                            cur,
                            entity="person",
                            entity_id=person_id,
                            field=field_name,
                            old=old,
                            new=hit.value,
                            rule_id=hit.rule_id,
                            confidence=hit.confidence,
                            reason="second phone kept off the primary field" if field_name == "notes" else None,
                        )
                for kind, person_id, field_name in reviews:
                    provenance.open_review(
                        cur,
                        kind=kind,
                        dedupe_key=f"{kind}:{person_id}:ocr",
                        person_id=person_id,
                        evidence={"field": field_name},
                    )
        GAPS.parent.mkdir(parents=True, exist_ok=True)
        with GAPS.open("w", encoding="utf-8") as handle:
            for row in ledger:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        stats["persons"] = len(persons)
        stats["gap_rows"] = len(ledger)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()
        provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run")
    for key in sorted(stats):
        if key.startswith(("gap:", "filled:", "filled_rule:", "conflict:")) or key in {
            "persons", "document_pages", "scanner_packets", "scanner_low", "scanner_unmatched",
            "letterhead_numbers", "letterhead_addresses", "bound", "ambiguous", "blocked", "phone_alternate", "skipped_junk",
        }:
            print(f"  {key} {stats[key]}")
    return 0


def _mark_ambiguous(candidate: Candidate, people: list[PersonOnInvoice], flags: dict) -> None:
    if candidate.block_name:
        for person in people:
            if person.full_name and names_compatible(candidate.block_name, person.full_name):
                flags[person.person_id][candidate.field].add("ambiguous")
        return
    if candidate.rule_id == "acta_child_dob":
        roles = {"beneficiario"}
    elif candidate.rule_id in {"acta_domicilio", "form_address", "street_line"}:
        roles = {"titular"}
    else:
        return
    for person in people:
        if person.role in roles:
            flags[person.person_id][candidate.field].add("ambiguous")


def _is_minor(rows: list[tuple[str, str | None]], birth_date) -> bool:
    if not rows or any(role != "beneficiario" for role, _parentesco in rows):
        return False
    return any(is_minor_beneficiario("beneficiario", parentesco, birth_date) for _role, parentesco in rows)


if __name__ == "__main__":
    raise SystemExit(main())
