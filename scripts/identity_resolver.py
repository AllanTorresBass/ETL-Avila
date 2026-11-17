#!/usr/bin/env python3
"""Find duplicate people (spelling variants, OCR noise) and merge or queue them.

Candidates come from blocks, never from all pairs:
- people on the same invoice
- beneficiaries of the same titular
- the same birth date
- a shared pair of phonetic name tokens

Each pair gets a name score (token-set, OCR-aware) adjusted by birth date and
context. Two different cédulas are never the same person. Pairs a reviewer
rejected are skipped.

- score ≥ 0.95 and identical birth date → auto-merge (``merge_person``)
- 0.75 ≤ score < 0.95 → ``duplicate_candidate`` review item
- otherwise ignored

  PYTHONPATH=scripts .venv/bin/python scripts/identity_resolver.py            # dry-run
  PYTHONPATH=scripts .venv/bin/python scripts/identity_resolver.py --apply
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

import provenance  # noqa: E402
from env_load import load_env  # noqa: E402
from person_upsert import fold_person_name, merge_person  # noqa: E402

AUTO_MERGE = 0.95
REVIEW = 0.75
MAX_BLOCK = 60
_STOP = {"de", "del", "la", "las", "los", "y", "da", "van", "von"}


@dataclass
class Person:
    id: str
    name: str
    ci: str | None = None
    birth_date: object = None
    phone: str | None = None
    created_at: object = None
    invoices: set = field(default_factory=set)
    roles: dict = field(default_factory=dict)
    titulars: set = field(default_factory=set)

    @property
    def tokens(self) -> list[str]:
        return [t for t in fold_person_name(self.name).split() if t not in _STOP and len(t) > 1]


def phonetic(token: str) -> str:
    """Spanish-ish sound key: v/b, z/s/c(e,i), y/i/e, silent h, doubled letters, final s."""
    t = token.lower()
    t = re.sub(r"(?<!c)h", "", t)
    t = t.replace("ll", "y").replace("qu", "k").replace("v", "b").replace("z", "s")
    t = re.sub(r"c(?=[ei])", "s", t)
    t = t.replace("c", "k").replace("y", "i").replace("e", "i")
    t = re.sub(r"(.)\1+", r"\1", t)
    if len(t) > 4 and t.endswith("s"):
        t = t[:-1]
    return t


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def token_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if phonetic(a) == phonetic(b):
        return 0.97
    if min(len(a), len(b)) >= 4 and _edit_distance_le1(a, b):
        return 0.92
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio * 0.9 if ratio >= 0.8 else 0.0


def name_score(a: list[str], b: list[str]) -> float:
    """Greedy token-set match; missing tokens on the longer name cost a little."""
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    remaining = list(long_)
    total = 0.0
    matched = 0
    for token in short:
        best_i, best = -1, 0.0
        for i, other in enumerate(remaining):
            sim = token_similarity(token, other)
            if sim > best:
                best_i, best = i, sim
        if best_i >= 0:
            remaining.pop(best_i)
            total += best
            matched += 1
    if matched < min(2, len(short)):
        return 0.0
    base = total / len(short)
    coverage = len(short) / len(long_)
    return base * (0.8 + 0.2 * coverage)


@dataclass
class Scored:
    a: Person
    b: Person
    name: float
    score: float
    dob_match: bool
    signals: list[str]


def score_pair(a: Person, b: Person) -> Scored | None:
    if a.ci and b.ci and a.ci != b.ci:
        return None
    n = name_score(a.tokens, b.tokens)
    if n <= 0:
        return None
    signals = [f"name:{n:.3f}"]
    score = n
    dob_match = bool(a.birth_date and b.birth_date and a.birth_date == b.birth_date)
    if a.birth_date and b.birth_date:
        if dob_match:
            score += 0.03
            signals.append("dob_equal")
        else:
            score -= 0.3
            signals.append("dob_differs")
    if a.titulars & b.titulars:
        score += 0.02
        signals.append("same_titular")
    if a.phone and b.phone and re.sub(r"\D", "", a.phone)[-7:] == re.sub(r"\D", "", b.phone)[-7:]:
        score += 0.03
        signals.append("same_phone")
    shared = a.invoices & b.invoices
    if shared:
        signals.append("same_invoice")
        # Same-name parent and child can sit on one invoice; never auto-merge a titular
        # with a beneficiary of that same invoice.
        if any({a.roles.get(i), b.roles.get(i)} == {"titular", "beneficiario"} for i in shared):
            signals.append("titular_vs_beneficiario")
    return Scored(a, b, n, min(score, 1.0), dob_match, signals)


def decide(s: Scored) -> str:
    if s.score >= AUTO_MERGE and s.name >= AUTO_MERGE - 0.03 and s.dob_match and (
        "titular_vs_beneficiario" not in s.signals
    ):
        return "merge"
    if s.score >= REVIEW:
        return "review"
    return "ignore"


def survivor_of(a: Person, b: Person) -> tuple[Person, Person]:
    def rank(p: Person):
        return (bool(p.ci), len(p.invoices), bool(p.birth_date), -(p.created_at.timestamp() if p.created_at else 0))

    return (a, b) if rank(a) >= rank(b) else (b, a)


def candidate_pairs(people: dict[str, Person]) -> set[tuple[str, str]]:
    blocks: dict[str, list[str]] = defaultdict(list)
    for p in people.values():
        for inv in p.invoices:
            blocks[f"inv:{inv}"].append(p.id)
        for t in p.titulars:
            blocks[f"tit:{t}"].append(p.id)
        if p.birth_date:
            blocks[f"dob:{p.birth_date}"].append(p.id)
        keys = sorted({phonetic(t) for t in p.tokens if len(t) >= 3})
        for x, y in itertools.combinations(keys, 2):
            blocks[f"ph:{x}|{y}"].append(p.id)
    pairs: set[tuple[str, str]] = set()
    for members in blocks.values():
        if len(members) < 2 or len(members) > MAX_BLOCK:
            continue
        for x, y in itertools.combinations(sorted(set(members)), 2):
            pairs.add((x, y))
    return pairs


def load_people(cur) -> dict[str, Person]:
    cur.execute(
        """
        SELECT id::text AS id, full_name, identity_number, birth_date, phone, created_at
        FROM avila.person WHERE full_name IS NOT NULL AND btrim(full_name) <> ''
        """
    )
    people = {
        r["id"]: Person(r["id"], r["full_name"], r["identity_number"], r["birth_date"], r["phone"], r["created_at"])
        for r in cur.fetchall()
    }
    cur.execute(
        """
        SELECT ip.invoice_id::text AS invoice_id, ip.person_id::text AS person_id, ip.role::text AS role,
               t.person_id::text AS titular_id
        FROM avila.invoice_person ip
        LEFT JOIN avila.invoice_person t ON t.invoice_id = ip.invoice_id AND t.role = 'titular'
        """
    )
    for r in cur.fetchall():
        p = people.get(r["person_id"])
        if not p:
            continue
        p.invoices.add(r["invoice_id"])
        p.roles[r["invoice_id"]] = r["role"]
        if r["titular_id"] and r["titular_id"] != p.id:
            p.titulars.add(r["titular_id"])
    return people


def _rejected_pairs(cur) -> set[tuple[str, str]]:
    cur.execute(
        """
        SELECT person_id::text AS a, other_person_id::text AS b FROM avila.review_item
        WHERE kind = 'duplicate_candidate' AND status = 'rejected'
        """
    )
    return {tuple(sorted((r["a"], r["b"]))) for r in cur.fetchall() if r["a"] and r["b"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, "identity_resolver", vars(args), apply=args.apply)
    stats: Counter = Counter()
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        people = load_people(cur)
        rejected = _rejected_pairs(cur)
        pairs = candidate_pairs(people)
        stats["people"] = len(people)
        stats["candidate_pairs"] = len(pairs)
        merged: dict[str, str] = {}
        scored = [s for x, y in pairs if (s := score_pair(people[x], people[y]))]
        stats["not_comparable"] = len(pairs) - len(scored)
        scored.sort(key=lambda s: -s.score)
        with provenance.source("derived", "identity_resolver"):
            for s in scored:
                key = tuple(sorted((s.a.id, s.b.id)))
                if key in rejected:
                    stats["skipped_rejected"] += 1
                    continue
                if s.a.id in merged or s.b.id in merged:
                    stats["skipped_already_merged"] += 1
                    continue
                action = decide(s)
                stats[action] += 1
                if action == "ignore":
                    continue
                survivor, alias = survivor_of(s.a, s.b)
                if action == "merge":
                    if args.apply:
                        merge_person(
                            cur, survivor.id, alias.id,
                            reason=f"identity_resolver score={s.score:.3f} {'+'.join(s.signals)}",
                        )
                    merged[alias.id] = survivor.id
                    continue
                provenance.open_review(
                    cur,
                    kind="duplicate_candidate",
                    dedupe_key=f"duplicate_candidate:{key[0]}:{key[1]}",
                    person_id=survivor.id,
                    other_person_id=alias.id,
                    evidence={"signals": s.signals, "survivor_rule": "ci>invoices>dob>oldest"},
                    score=round(s.score, 3),
                )
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    provenance.finish_run(url, dict(stats))
    print("apply" if args.apply else "dry-run", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
