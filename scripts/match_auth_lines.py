#!/usr/bin/env python3
"""Link workbook authorization lines to invoices and store why each line is or is not linked.

Candidates for a line are invoices of the same account that carry the line's
person, carry its titular, or share its CLAVE. Score (capped at 1.0):

- CLAVE equal ............................................. +0.60
- line person on the invoice ............................. +0.40
- line titular on the invoice (person not on it) ......... +0.30
- request/service date 0–60 days before the issue date ... +0.20 (after it, or over 180 days before: −0.20)
- no exact date, issue month is the period month or next . +0.10 (before the period month, or over 6 months after: −0.20)
- amount within 2 % of the invoice total (Bs or USD) ..... +0.15
- service description overlaps fiscal service lines ...... +0.10
- the invoice is the line's only candidate ............... +0.10

Best ≥ 0.70 and ahead of the runner-up by ≥ 0.15 → link (provenance; the person
joins the invoice as beneficiario only when the CLAVE matched). Best ≥ 0.45
otherwise → ``auth_match`` review item. Every line gets ``match_status``,
``match_score``, ``match_signals``, and ``matched_at``. Lines a person linked in
/autorizaciones (``match_status = 'staff'``) are never rescored. Idempotent:
linked lines are skipped unless --relink. On --apply, open ``auth_match`` items
this run did not refresh are deleted.

  PYTHONPATH=scripts .venv/bin/python scripts/match_auth_lines.py            # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/match_auth_lines.py --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import account_code_from_label  # noqa: E402
from invoice_rules import classify, fold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXTRACT_JSONL = ROOT / "output" / "invoices" / "fiscal-extract.jsonl"

AUTO_LINK = 0.70
MARGIN = 0.15
REVIEW = 0.45
WINDOW_DAYS = 60
STALE_DAYS = 180
MIN_YEAR = 2000
_WORD = re.compile(r"[A-Z]{4,}")
_STOP = {"CONSULTA", "SERVICIO", "SERVICIOS", "MEDICO", "MEDICA", "PARA", "CON", "DEL"}


@dataclass
class Line:
    id: str
    person_id: str | None
    clave: str | None
    account: str | None
    when: dt.date | None
    amounts: tuple[float, ...]
    words: set[str]
    titular_id: str | None = None
    period: dt.date | None = None


@dataclass
class Invoice:
    id: str
    account: str | None
    issue_date: dt.date | None
    clave: str | None
    totals: tuple[float, ...]
    people: set[str] = field(default_factory=set)
    words: set[str] = field(default_factory=set)


def norm_clave(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits.lstrip("0") or None if len(digits) >= 4 else None


def words(text: str | None) -> set[str]:
    return {w for w in _WORD.findall(fold(text or "")) if w not in _STOP}


def line_date(*candidates: dt.date | None) -> dt.date | None:
    """First usable date; workbook cells with no date read back as 1899/1900."""
    for value in candidates:
        if value and value.year >= MIN_YEAR:
            return value
    return None


def line_account(source_file: str) -> str | None:
    try:
        return account_code_from_label(classify(source_file).account)
    except Exception:  # noqa: BLE001
        return None


def _months_after(issue: dt.date, period: dt.date) -> int:
    return (issue.year - period.year) * 12 + issue.month - period.month


def score(line: Line, inv: Invoice, *, only_candidate: bool) -> tuple[float, list[str]]:
    total = 0.0
    signals: list[str] = []
    if line.clave and inv.clave and line.clave == inv.clave:
        total += 0.60
        signals.append("clave")
    if line.person_id and line.person_id in inv.people:
        total += 0.40
        signals.append("person")
    elif line.titular_id and line.titular_id in inv.people:
        total += 0.30
        signals.append("titular")
    if line.when and inv.issue_date:
        delta = (inv.issue_date - line.when).days
        if 0 <= delta <= WINDOW_DAYS:
            total += 0.20
            signals.append(f"date:{delta}d")
        elif delta < 0:
            total -= 0.20
            signals.append("date:after_issue")
        elif delta > STALE_DAYS:
            total -= 0.20
            signals.append("date:stale")
    elif line.period and inv.issue_date:
        months = _months_after(inv.issue_date, line.period)
        if months in (0, 1):
            total += 0.10
            signals.append(f"period:{months}m")
        elif months < 0:
            total -= 0.20
            signals.append("period:after_issue")
        elif months > STALE_DAYS // 30:
            total -= 0.20
            signals.append("period:stale")
    if line.amounts and inv.totals and any(
        a and t and abs(a - t) <= 0.02 * max(a, t) for a in line.amounts for t in inv.totals
    ):
        total += 0.15
        signals.append("amount")
    if line.words and inv.words and len(line.words & inv.words) / len(line.words | inv.words) >= 0.2:
        total += 0.10
        signals.append("service")
    if only_candidate and signals:
        total += 0.10
        signals.append("only_candidate")
    return min(total, 1.0), signals


def decide(ranked: list[tuple[float, str, list[str]]]) -> str:
    if not ranked:
        return "none"
    best = ranked[0][0]
    runner = ranked[1][0] if len(ranked) > 1 else 0.0
    if best >= AUTO_LINK and best - runner >= MARGIN:
        return "link"
    if best >= REVIEW:
        return "review"
    return "none"


def rank_line(line: Line, candidates: list[Invoice]) -> list[tuple[float, str, list[str]]]:
    only = len(candidates) == 1
    ranked = []
    for inv in candidates:
        if line.account and inv.account and line.account != inv.account:
            continue
        s, signals = score(line, inv, only_candidate=only)
        ranked.append((round(s, 3), inv.id, signals))
    ranked.sort(key=lambda r: -r[0])
    return [r for r in ranked if r[0] > 0] or ranked[:1]


def candidate_pool(
    line: Line,
    by_person: dict[str, list[Invoice]],
    by_clave: dict[str, list[Invoice]],
) -> dict[str, Invoice]:
    pool = {inv.id: inv for inv in by_person.get(line.person_id or "", [])}
    pool.update({inv.id: inv for inv in by_person.get(line.titular_id or "", [])})
    pool.update({inv.id: inv for inv in by_clave.get(line.clave or "", [])})
    return pool


def unlinked_status(line: Line, ranked: list[tuple[float, str, list[str]]], action: str) -> str:
    """match_status for a line this run did not link. ``ranked`` holds same-insurer candidates only."""
    if action == "review":
        return "review"
    if not line.person_id and not line.titular_id and not line.clave:
        return "no_person"
    if not ranked:
        return "no_candidate"
    return "low_score"


@dataclass
class Stored:
    invoice_id: str | None
    status: str | None
    score: float | None
    signals: list[str] | None
    duplicate: bool
    reviewed: bool


def _load(cur, relink: bool) -> tuple[list[Line], dict[str, Invoice], dict[str, Stored]]:
    cur.execute(
        """
        SELECT i.id::text AS id, a.code AS account, i.issue_date, i.clave, i.total_bs, i.total_usd
        FROM avila.invoice i LEFT JOIN avila.account a ON a.id = i.account_id
        """
    )
    invoices = {
        r["id"]: Invoice(
            r["id"], r["account"], r["issue_date"], norm_clave(r["clave"]),
            tuple(float(x) for x in (r["total_bs"], r["total_usd"]) if x),
        )
        for r in cur.fetchall()
    }
    cur.execute("SELECT invoice_id::text AS i, person_id::text AS p FROM avila.invoice_person")
    for r in cur.fetchall():
        if r["i"] in invoices:
            invoices[r["i"]].people.add(r["p"])
    if EXTRACT_JSONL.is_file():
        for raw in EXTRACT_JSONL.read_text(encoding="utf-8").splitlines():
            item = json.loads(raw)
            inv = invoices.get(item["invoice_id"])
            if inv:
                inv.words = words(" ".join(item.get("services") or []))
    cur.execute(
        """
        SELECT al.id::text AS id, al.person_id::text AS person_id, al.titular_person_id::text AS titular_id,
               al.clave_rms, al.source_file, al.request_date, al.service_date, al.period_month,
               al.amount_bs, al.amount_usd, al.authorized_amount, al.service_description,
               al.invoice_id::text AS invoice_id, al.duplicate_of IS NOT NULL AS duplicate,
               al.match_status, al.match_score::float8 AS match_score, al.match_signals,
               EXISTS (
                 SELECT 1 FROM avila.review_item r
                 WHERE r.authorization_line_id = al.id AND r.kind = 'auth_match' AND r.status = 'accepted'
               ) AS reviewed
        FROM avila.authorization_line al
        """
    )
    lines: list[Line] = []
    stored: dict[str, Stored] = {}
    for r in cur.fetchall():
        stored[r["id"]] = Stored(
            r["invoice_id"], r["match_status"], r["match_score"], r["match_signals"], r["duplicate"], r["reviewed"]
        )
        if r["duplicate"] or r["match_status"] == "staff" or (r["invoice_id"] and not relink):
            continue
        lines.append(
            Line(
                r["id"], r["person_id"], norm_clave(r["clave_rms"]), line_account(r["source_file"]),
                line_date(r["request_date"], r["service_date"]),
                tuple(float(x) for x in (r["amount_bs"], r["amount_usd"], r["authorized_amount"]) if x),
                words(r["service_description"]),
                titular_id=r["titular_id"],
                period=r["period_month"],
            )
        )
    return lines, invoices, stored


def main() -> int:
    import psycopg
    from psycopg.rows import dict_row

    import provenance
    from env_load import load_env
    from upload_documents_to_blob import link_invoice_person

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--relink", action="store_true", help="Re-score lines that already have an invoice")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, "match_auth_lines", vars(args), apply=args.apply)
    stats: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        lines, invoices, stored = _load(cur, args.relink)
        by_person: dict[str, list[Invoice]] = defaultdict(list)
        by_clave: dict[str, list[Invoice]] = defaultdict(list)
        for inv in invoices.values():
            for pid in inv.people:
                by_person[pid].append(inv)
            if inv.clave:
                by_clave[inv.clave].append(inv)
        stats["lines"] = len(lines)

        outcome: dict[str, tuple[str, float | None, list[str] | None]] = {}
        for line_id, row in stored.items():
            if row.duplicate:
                outcome[line_id] = ("duplicate", None, None)
            elif row.status == "staff":
                continue
            elif row.invoice_id and not args.relink:
                status = "review" if row.reviewed else "linked"
                outcome[line_id] = (status, row.score, row.signals)

        with provenance.source("derived", "match_auth_lines"), conn.pipeline():
            for line in lines:
                pool = candidate_pool(line, by_person, by_clave)
                ranked = rank_line(line, list(pool.values()))
                action = decide(ranked)
                stats[action] += 1
                best_score, invoice_id, signals = ranked[0] if ranked else (None, None, None)
                if action != "link":
                    status = unlinked_status(line, ranked, action)
                    stats[f"status:{status}"] += 1
                    outcome[line.id] = (status, best_score, signals)
                if action == "none":
                    continue
                if action == "review":
                    provenance.open_review(
                        cur,
                        kind="auth_match",
                        dedupe_key=f"auth_match:{line.id}",
                        authorization_line_id=line.id,
                        invoice_id=invoice_id,
                        person_id=line.person_id,
                        evidence={"top": [{"invoice_id": i, "score": s, "signals": g} for s, i, g in ranked[:3]]},
                        score=best_score,
                    )
                    continue
                stats["status:linked"] += 1
                outcome[line.id] = ("linked", best_score, signals)
                for sig in signals:
                    stats[f"signal:{sig.split(':')[0]}"] += 1
                previous = stored[line.id].invoice_id
                if previous == invoice_id:
                    continue
                cur.execute(
                    "UPDATE avila.authorization_line SET invoice_id = %s, updated_at = now() WHERE id = %s",
                    (invoice_id, line.id),
                )
                stats["newly_linked"] += 1
                provenance.record(
                    cur, entity="authorization_line", entity_id=line.id, field="invoice_id",
                    old=previous, new=invoice_id, rule_id="match_auth_lines", confidence=best_score,
                    reason="+".join(signals),
                )
                if line.person_id and line.person_id not in invoices[invoice_id].people:
                    if "clave" not in signals:
                        stats["person_not_added_without_clave"] += 1
                        continue
                    link_invoice_person(
                        cur, invoice_id, line.person_id, "beneficiario",
                        source="auth_match", rule_id="auth_line_person",
                    )
                    invoices[invoice_id].people.add(line.person_id)
                    stats["person_added_to_invoice"] += 1

            for line_id, (status, best, signals) in outcome.items():
                row = stored[line_id]
                if (row.status, row.score, row.signals) == (status, best, signals):
                    continue
                stats["status_written"] += 1
                cur.execute(
                    """
                    UPDATE avila.authorization_line
                    SET match_status = %s, match_score = %s, match_signals = %s, matched_at = now()
                    WHERE id = %s::uuid
                    """,
                    (status, best, signals, line_id),
                )
        if args.apply:
            cur.execute(
                """
                DELETE FROM avila.review_item
                WHERE kind = 'auth_match' AND status = 'open' AND run_id IS DISTINCT FROM %s
                """,
                (provenance.current_run_id(),),
            )
            stats["stale_review_deleted"] = cur.rowcount
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run", dict(sorted(stats.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
