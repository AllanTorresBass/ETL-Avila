#!/usr/bin/env python3
"""Classify cédulas that have no factura, authorization, or document.

Reads the gitignored list at output/runs/never-linked.md. Dry-run is the
default and writes output/runs/never-linked-plan.json. Stdout is counts.

  PYTHONPATH=scripts .venv/bin/python scripts/repair_never_linked.py
  PYTHONPATH=scripts .venv/bin/python scripts/repair_never_linked.py --reviews

``--reviews`` opens duplicate_candidate for a one-digit twin that shares a
name. It does not merge people and it does not create facturas. A factura
link still requires the printed page.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ocr_invoice_pages  # noqa: E402
import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from fiscal_extract import extract  # noqa: E402
from workbook_enrichment.orphan_cedulas import (  # noqa: E402
    LEAVE,
    LINK_BENEFICIARIO,
    PROMOTE_TITULAR,
    REVIEW_DUPLICATE,
    cedula_digits,
    decide_never_linked,
    one_digit_apart,
    shares_name_token,
)

ROOT = Path(__file__).resolve().parents[1]
LIST_PATH = ROOT / "output" / "runs" / "never-linked.md"
PLAN_PATH = ROOT / "output" / "runs" / "never-linked-plan.json"
RANK = {REVIEW_DUPLICATE: 3, LINK_BENEFICIARIO: 2, PROMOTE_TITULAR: 1, LEAVE: 0}


def load_list(path: Path) -> list[dict]:
    people = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| Cédula") or line.startswith("| ---"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        digits = cedula_digits(parts[0]) if parts else ""
        if not digits:
            continue
        people.append({"ci": digits, "name": parts[1] if len(parts) > 1 else ""})
    return people


def _own_number(number: str | None, invoices: dict[str, dict]) -> str | None:
    digits = cedula_digits(number)
    if not digits or digits != str(number).strip().lstrip("0"):
        # Keep a exact stored key too. "00018092" and "18092" are the same factura.
        pass
    if not digits:
        return None
    bare = str(int(digits))
    for key in (bare, digits, digits.zfill(5), digits.zfill(6)):
        if key in invoices:
            return key
    return None


def scan_pages(wanted: set[str]) -> dict[str, list[dict]]:
    hits: dict[str, list[dict]] = defaultdict(list)
    root = ocr_invoice_pages.cache_path(".").parent
    if not root.is_dir():
        return hits
    pattern = re.compile(r"(?<!\d)(?:" + "|".join(sorted(wanted, key=len, reverse=True)) + r")(?!\d)")
    for path in root.rglob("*.json"):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found = set(pattern.findall(raw.replace(".", "")))
        if not found:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        text = "\n".join((page.get("text") or "") for page in data.get("pages") or [])
        fields = extract(text)
        patient = cedula_digits(fields.patient_ci)
        titular = cedula_digits(fields.titular_ci)
        for ci in found:
            if ci != patient and ci != titular:
                continue
            hits[ci].append(
                {
                    "path": data.get("path") or "",
                    "invoice_number": fields.invoice_number,
                    "as_patient": ci == patient,
                    "as_titular": ci == titular,
                    "other_ci": titular if ci == patient else patient,
                }
            )
    return hits


def classify(people: list[dict], linked: list[dict], pages: dict[str, list[dict]], invoices: dict[str, dict]) -> list[dict]:
    by_len: dict[int, list[dict]] = defaultdict(list)
    for row in linked:
        by_len[len(row["ci"])].append(row)
    plans = []
    for person in people:
        twins = [
            row
            for row in by_len.get(len(person["ci"]), [])
            if one_digit_apart(person["ci"], row["ci"]) and shares_name_token(person["name"], row["full_name"])
        ]
        best = LEAVE
        chosen = []
        for page in pages.get(person["ci"], []):
            own = _own_number(page["invoice_number"], invoices)
            stored = invoices.get(own or "")
            slot_empty = stored is None or stored["titulares"] == 0
            action = decide_never_linked(
                person["ci"],
                fiscal_titular_ci=page["other_ci"] if page["as_patient"] else person["ci"],
                fiscal_patient_ci=person["ci"] if page["as_patient"] else page["other_ci"],
                invoice_number=page["invoice_number"],
                titular_slot_empty=slot_empty and page["as_titular"],
                twin_shares_name=bool(twins),
            )
            if RANK[action] > RANK[best]:
                best = action
                chosen = [page]
            elif action == best and action != LEAVE:
                chosen.append(page)
        if not pages.get(person["ci"]):
            best = decide_never_linked(person["ci"], twin_shares_name=bool(twins))
        plans.append(
            {
                "ci": person["ci"],
                "action": best,
                "invoices": sorted({page["invoice_number"] or "" for page in chosen if page.get("invoice_number")}),
                "paths": sorted({page["path"] for page in chosen if page.get("path")}),
                "twins": [{"ci": row["ci"], "person_id": row["id"]} for row in twins],
            }
        )
    return plans


def open_reviews(url: str, plans: list[dict], people_by_ci: dict[str, str]) -> Counter:
    stats: Counter = Counter()
    provenance.start_run(url, "repair_never_linked_reviews", {"reviews": True}, apply=True)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        for plan in plans:
            if plan["action"] != REVIEW_DUPLICATE:
                continue
            person_id = people_by_ci.get(plan["ci"])
            if not person_id:
                stats["missing_person"] += 1
                continue
            for twin in plan["twins"]:
                pair = tuple(sorted((person_id, twin["person_id"])))
                provenance.open_review(
                    cur,
                    kind="duplicate_candidate",
                    dedupe_key=f"duplicate_candidate:{pair[0]}:{pair[1]}",
                    person_id=person_id,
                    other_person_id=twin["person_id"],
                    evidence={"signals": ["one_digit", "shared_name_token"], "source": "never_linked"},
                )
                stats["reviews"] += 1
        conn.commit()
    provenance.finish_run(url, dict(stats))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", action="store_true")
    args = parser.parse_args()
    if not LIST_PATH.is_file():
        print("list_missing=1")
        return 1
    people = load_list(LIST_PATH)
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id::text AS id,
                   regexp_replace(p.identity_number, '\\D', '', 'g') AS ci,
                   p.full_name
            FROM avila.person p
            WHERE p.identity_type = 'cedula'
              AND coalesce(p.identity_number, '') <> ''
              AND EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id)
            """
        )
        linked = list(cur.fetchall())
        cur.execute(
            """
            SELECT i.invoice_number,
                   count(ip.person_id) FILTER (WHERE ip.role = 'titular')::int AS titulares
            FROM avila.invoice i
            LEFT JOIN avila.invoice_person ip ON ip.invoice_id = i.id
            GROUP BY i.invoice_number
            """
        )
        invoices = {row["invoice_number"]: row for row in cur.fetchall()}
        cur.execute(
            """
            SELECT id::text AS id, regexp_replace(identity_number, '\\D', '', 'g') AS ci
            FROM avila.person
            WHERE identity_type = 'cedula'
              AND regexp_replace(identity_number, '\\D', '', 'g') = ANY(%s)
            """,
            ([person["ci"] for person in people],),
        )
        people_by_ci = {row["ci"]: row["id"] for row in cur.fetchall()}
    pages = scan_pages({person["ci"] for person in people})
    plans = classify(people, linked, pages, invoices)
    counts = Counter(plan["action"] for plan in plans)
    PLAN_PATH.write_text(
        json.dumps({"counts": dict(counts), "people": plans}, indent=2),
        encoding="utf-8",
    )
    if args.reviews:
        stats = open_reviews(url, plans, people_by_ci)
        print(f"reviews={stats['reviews']} missing_person={stats['missing_person']}")
    print(
        " ".join(f"{action}={counts[action]}" for action in (LINK_BENEFICIARIO, PROMOTE_TITULAR, REVIEW_DUPLICATE, LEAVE))
        + f" people={len(plans)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
