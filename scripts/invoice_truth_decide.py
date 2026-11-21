#!/usr/bin/env python3
"""Mark each factura self, pair, or review from the truth file. No database.

  PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_decide.py

Reads output/runs/invoice-truth.jsonl.
Writes output/runs/invoice-truth-decisions.jsonl and a counts-only markdown report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from person_name_gate import is_date_like_identity, sanitize_person_name  # noqa: E402
from upload_documents_to_blob import _names_refer_to_same_person  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IN_JSONL = ROOT / "output" / "runs" / "invoice-truth.jsonl"
OUT_JSONL = ROOT / "output" / "runs" / "invoice-truth-decisions.jsonl"
OUT_MD = ROOT / "output" / "runs" / "invoice-truth-decisions.md"

REVIEW_REASONS = (
    "no_titular_ci",
    "fiscal_card_mismatch",
    "unassigned_cards",
    "acta_only",
    "unnamed_card",
)


def _ci(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not (6 <= len(digits) <= 9) or is_date_like_identity(digits):
        return None
    return digits


def _name(value: str | None) -> str | None:
    return sanitize_person_name(value)


def _card_cis(cards: list[dict]) -> list[str]:
    seen: list[str] = []
    for card in cards:
        for raw in card.get("cedulas") or []:
            number = _ci(raw)
            if number and number not in seen:
                seen.append(number)
    return seen


def _card_for_ci(cards: list[dict], number: str | None) -> dict | None:
    if not number:
        return None
    matches = [card for card in cards if number in {_ci(raw) for raw in card.get("cedulas") or []}]
    for card in matches:
        if _name(card.get("name")):
            return card
    return matches[0] if matches else None


def _card_for_name(cards: list[dict], name: str | None, titular_ci: str) -> tuple[dict | None, str | None]:
    """A second card whose name is the patient, and a cédula on it that is not the titular's."""
    if not name:
        return None, None
    for card in cards:
        card_name = _name(card.get("name"))
        if not card_name or not _names_refer_to_same_person(card_name, name):
            continue
        other = [number for number in (_ci(raw) for raw in card.get("cedulas") or []) if number and number != titular_ci]
        return card, (other[0] if other else None)
    return None, None


def _blank(row: dict) -> dict:
    return {
        "invoice_id": row.get("invoice_id"),
        "invoice_number": row.get("invoice_number"),
        "outcome": "review",
        "reason": None,
        "titular_name": None,
        "titular_ci": None,
        "titular_source": None,
        "titular_document_id": None,
        "titular_page_index": None,
        "titular_backup_path": None,
        "beneficiario_name": None,
        "beneficiario_ci": None,
        "beneficiario_source": None,
        "beneficiario_document_id": None,
        "beneficiario_page_index": None,
        "beneficiario_backup_path": None,
    }


def _review(row: dict, reason: str) -> dict:
    decision = _blank(row)
    decision["reason"] = reason
    return decision


def _attach_card(decision: dict, prefix: str, card: dict | None) -> None:
    if not card:
        return
    decision[f"{prefix}_document_id"] = card.get("document_id")
    decision[f"{prefix}_page_index"] = card.get("page_index")
    decision[f"{prefix}_backup_path"] = card.get("backup_path")


def decide_record(row: dict) -> dict:
    """Closed outcome for one truth row. First matching review reason wins."""
    cards = list(row.get("cards") or [])
    card_cis = _card_cis(cards)
    fiscal_ci = _ci(row.get("fiscal_titular_ci"))
    fiscal_name = _name(row.get("fiscal_titular_name"))
    patient_name = _name(row.get("fiscal_patient_name"))
    patient_ci = _ci(row.get("fiscal_patient_ci"))
    acta = [number for number in (_ci(raw) for raw in row.get("acta_parent_cis") or []) if number and number not in card_cis]
    path_name = _name(row.get("path_name"))

    # Acta-only is the specific form of "no card and no fiscal cédula".
    if not card_cis and not fiscal_ci:
        if acta:
            return _review(row, "acta_only")
        return _review(row, "no_titular_ci")

    if fiscal_ci and card_cis and fiscal_ci not in card_cis:
        return _review(row, "fiscal_card_mismatch")

    titular_ci = None
    titular_source = None
    if fiscal_ci and (not card_cis or fiscal_ci in card_cis):
        titular_ci = fiscal_ci
        titular_source = "fiscal_ocr"
    elif not fiscal_ci and len(card_cis) == 1:
        titular_ci = card_cis[0]
        titular_source = "ocr_cedula"

    def placed(number: str) -> bool:
        if titular_ci and number == titular_ci:
            return True
        if patient_ci and number == patient_ci:
            return True
        card = _card_for_ci(cards, number)
        card_name = _name(card.get("name")) if card else None
        return bool(patient_name and card_name and _names_refer_to_same_person(card_name, patient_name))

    if len(card_cis) >= 2 and (titular_ci is None or not all(placed(number) for number in card_cis)):
        return _review(row, "unassigned_cards")

    if not titular_ci:
        return _review(row, "no_titular_ci")

    titular_card = _card_for_ci(cards, titular_ci)
    titular_name = (_name(titular_card.get("name")) if titular_card else None) or fiscal_name
    if not titular_name:
        return _review(row, "unnamed_card")

    decision = _blank(row)
    decision["titular_name"] = titular_name
    decision["titular_ci"] = titular_ci
    decision["titular_source"] = titular_source
    _attach_card(decision, "titular", titular_card)
    if titular_card is None:
        decision["titular_backup_path"] = row.get("fiscal_backup_path")
        decision["titular_page_index"] = row.get("fiscal_page_index")

    same_ci = bool(patient_ci and patient_ci == titular_ci)
    same_name = bool(patient_name and _names_refer_to_same_person(patient_name, titular_name))
    fiscal_patient = bool(patient_name or patient_ci)

    if fiscal_patient and (same_ci or same_name):
        decision["outcome"] = "self"
        decision["reason"] = "self"
        return decision

    if fiscal_patient and patient_name and not same_name and not same_ci:
        ben_ci = patient_ci if patient_ci and patient_ci != titular_ci else None
        ben_card, card_ci = _card_for_name(cards, patient_name, titular_ci)
        if ben_ci is None:
            ben_ci = card_ci
            chosen = ben_card
        else:
            chosen = ben_card if _ci_on_card(ben_card, ben_ci, titular_ci) else _card_for_ci(cards, ben_ci)
        decision["outcome"] = "pair"
        decision["reason"] = "pair"
        decision["beneficiario_name"] = patient_name
        decision["beneficiario_ci"] = ben_ci
        decision["beneficiario_source"] = "fiscal_ocr"
        _attach_card(decision, "beneficiario", _other_page(chosen, titular_card))
        return decision

    if fiscal_patient and patient_ci and patient_ci != titular_ci and not patient_name:
        ben_card = _card_for_ci(cards, patient_ci)
        ben_name = _name(ben_card.get("name")) if ben_card else None
        decision["outcome"] = "pair"
        decision["reason"] = "pair"
        decision["beneficiario_name"] = ben_name
        decision["beneficiario_ci"] = patient_ci
        decision["beneficiario_source"] = "fiscal_ocr"
        _attach_card(decision, "beneficiario", _other_page(ben_card, titular_card))
        return decision

    if not fiscal_patient and path_name and not _names_refer_to_same_person(path_name, titular_name):
        ben_card, card_ci = _card_for_name(cards, path_name, titular_ci)
        decision["outcome"] = "pair"
        decision["reason"] = "pair"
        decision["beneficiario_name"] = path_name
        decision["beneficiario_ci"] = card_ci
        decision["beneficiario_source"] = "path"
        _attach_card(decision, "beneficiario", ben_card if card_ci else None)
        return decision

    decision["outcome"] = "self"
    decision["reason"] = "self"
    return decision


def _other_page(card: dict | None, titular_card: dict | None) -> dict | None:
    """A collage that holds both cédulas stays with the titular."""
    if not card:
        return None
    if titular_card and card.get("document_id") and card.get("document_id") == titular_card.get("document_id"):
        return None
    return card


def _ci_on_card(card: dict | None, ben_ci: str | None, titular_ci: str) -> bool:
    if not card or not ben_ci:
        return False
    numbers = {_ci(raw) for raw in card.get("cedulas") or []}
    return ben_ci in numbers and ben_ci != titular_ci


def render_md(stats: Counter) -> str:
    lines = [
        "# Invoice truth decisions",
        "",
        "Counts only. Names and cédulas stay in `invoice-truth-decisions.jsonl`.",
        "",
        "| Outcome | Count |",
        "| --- | ---: |",
        f"| self | {stats['self']} |",
        f"| pair | {stats['pair']} |",
    ]
    for reason in REVIEW_REASONS:
        lines.append(f"| review / {reason} | {stats[reason]} |")
    lines.append(f"| **Total** | **{stats['invoices']}** |")
    lines.append("")
    return "\n".join(lines)


def decide_rows(rows: list[dict]) -> tuple[list[dict], Counter]:
    stats: Counter = Counter()
    decisions = []
    for row in rows:
        decision = decide_record(row)
        decisions.append(decision)
        stats["invoices"] += 1
        if decision["outcome"] == "review":
            stats[decision["reason"]] += 1
        else:
            stats[decision["outcome"]] += 1
    for key in ("self", "pair", *REVIEW_REASONS):
        stats.setdefault(key, 0)
    return decisions, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", type=Path, default=IN_JSONL)
    args = parser.parse_args()
    if not args.input.is_file():
        sys.exit(f"missing {args.input.name}")
    rows = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    decisions, stats = decide_rows(rows)
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as out:
        for decision in decisions:
            out.write(json.dumps(decision, ensure_ascii=False) + "\n")
    OUT_MD.write_text(render_md(stats), encoding="utf-8")
    print(
        "invoices",
        stats["invoices"],
        "self",
        stats["self"],
        "pair",
        stats["pair"],
        "review",
        sum(stats[reason] for reason in REVIEW_REASONS),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
