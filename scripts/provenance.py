"""Run tracking, field provenance, and the review queue (sql/006).

How / when / where / why for every write:
- how  → ``rule_id`` (closed vocabulary, see RULES)
- when → ``created_at`` + ``etl_run`` window
- where → ``source_kind`` + ``source_ref`` (workbook file:sheet:row, backup path#page, document id)
- why  → ``reason`` + ``confidence``

Values are stored as short hashes, never as text: provenance must not become a
second copy of PHI. Scripts call ``start_run`` once; helpers pick the run id up
from a context variable so signatures stay small.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import psycopg

ROOT = Path(__file__).resolve().parents[1]

_RUN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("avila_run_id", default=None)
_SOURCE: contextvars.ContextVar[tuple[str, str | None] | None] = contextvars.ContextVar(
    "avila_source", default=None
)

SOURCE_KINDS = {"workbook", "ocr", "path", "case_evidence", "manual", "review", "derived"}

REVIEW_KINDS = {
    "duplicate_candidate",
    "ci_conflict",
    "workbook_titular",
    "multiple_ci",
    "dob_conflict",
    "phone_conflict",
    "address_conflict",
    "auth_match",
    "segment_review",
    "acta_titular",
}

# invoice_person.source values (sql/006 check constraint).
ROLE_SOURCES = {
    "workbook",
    "path",
    "ocr",
    "ocr_cedula",
    "fiscal_ocr",
    "scan_packet",
    "auth_match",
    "resolver",
    "review",
    "case_evidence",
    "manual",
    "legacy_unknown",
}

# Sources that may be replaced by any stronger evidence.
WEAK_ROLE_SOURCES = ("legacy_unknown",)

counters: Counter[str] = Counter()


def value_hash(value: Any) -> str | None:
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    text = " ".join(text.split()).casefold()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.strip() or None


def current_run_id() -> str | None:
    return _RUN_ID.get()


def current_source() -> tuple[str, str | None] | None:
    return _SOURCE.get()


def start_run(url: str, script: str, args: dict | None = None, *, apply: bool) -> str:
    """Insert an etl_run row on its own connection so dry-run rollbacks keep it."""
    counters.clear()
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute(
            """
            INSERT INTO avila.etl_run (script, args, git_sha, mode)
            VALUES (%s, %s::jsonb, %s, %s) RETURNING id
            """,
            (script, json.dumps(args or {}, default=str), _git_sha(), "apply" if apply else "dry"),
        ).fetchone()
    run_id = str(row[0])
    _RUN_ID.set(run_id)
    return run_id


def finish_run(url: str, extra: dict | None = None) -> None:
    run_id = _RUN_ID.get()
    if not run_id:
        return
    payload = dict(counters)
    if extra:
        payload.update({k: v for k, v in extra.items() if isinstance(v, (int, float, str))})
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "UPDATE avila.etl_run SET finished_at = now(), counters = %s::jsonb WHERE id = %s",
            (json.dumps(payload), run_id),
        )
    write_run_report(run_id, payload)


def write_run_report(run_id: str, payload: dict) -> Path:
    """Counts-only markdown summary under output/runs/ (git-ignored)."""
    out_dir = ROOT / "output" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.md"
    lines = [f"# ETL run {run_id}", "", "| Counter | Value |", "| --- | ---: |"]
    for key in sorted(payload):
        lines.append(f"| {key} | {payload[key]} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@contextlib.contextmanager
def source(kind: str, ref: str | None = None) -> Iterator[None]:
    """Default source_kind/source_ref for writes inside the block."""
    if kind not in SOURCE_KINDS:
        raise ValueError(f"unknown source_kind {kind}")
    token = _SOURCE.set((kind, ref))
    try:
        yield
    finally:
        _SOURCE.reset(token)


def record(
    cur,
    *,
    entity: str,
    entity_id: Any,
    field: str,
    old: Any,
    new: Any,
    rule_id: str,
    source_kind: str | None = None,
    source_ref: str | None = None,
    confidence: float | None = None,
    reason: str | None = None,
) -> bool:
    """Record one field change. No-op when the value did not change."""
    old_h, new_h = value_hash(old), value_hash(new)
    if old_h == new_h:
        return False
    ctx = _SOURCE.get()
    kind = source_kind or (ctx[0] if ctx else "derived")
    ref = source_ref if source_ref is not None else (ctx[1] if ctx else None)
    cur.execute(
        """
        INSERT INTO avila.field_provenance (
          entity, entity_id, field, old_value_hash, new_value_hash,
          source_kind, source_ref, rule_id, confidence, reason, run_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            entity,
            str(entity_id),
            field,
            old_h,
            new_h,
            kind,
            ref,
            rule_id,
            confidence,
            reason,
            _RUN_ID.get(),
        ),
    )
    counters[f"prov:{rule_id}"] += 1
    return True


def open_review(
    cur,
    *,
    kind: str,
    dedupe_key: str,
    person_id: Any = None,
    other_person_id: Any = None,
    invoice_id: Any = None,
    document_id: Any = None,
    authorization_line_id: Any = None,
    evidence: dict | None = None,
    score: float | None = None,
) -> None:
    """Create or refresh an open review item. Resolved items are left alone."""
    if kind not in REVIEW_KINDS:
        raise ValueError(f"unknown review kind {kind}")
    cur.execute(
        """
        INSERT INTO avila.review_item (
          kind, dedupe_key, person_id, other_person_id, invoice_id, document_id,
          authorization_line_id, evidence, score, run_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        ON CONFLICT (dedupe_key) DO UPDATE SET
          evidence = EXCLUDED.evidence,
          score = EXCLUDED.score,
          run_id = EXCLUDED.run_id,
          updated_at = now()
        WHERE avila.review_item.status = 'open'
        """,
        (
            kind,
            dedupe_key,
            _s(person_id),
            _s(other_person_id),
            _s(invoice_id),
            _s(document_id),
            _s(authorization_line_id),
            json.dumps(evidence or {}, default=str),
            score,
            _RUN_ID.get(),
        ),
    )
    counters[f"review:{kind}"] += 1


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None
