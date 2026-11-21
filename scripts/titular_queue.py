#!/usr/bin/env python3
"""Score all titulares into P0–P3 cohorts for one-by-one dossier processing.

Writes:
  output/persons/_queue/queue.jsonl   — full rows (PHI; git-ignored)
  output/persons/_queue/progress.md   — counts only
  output/runs/titular_queue_*.md      — counts-only report (also git-ignored under runs/)

Stdout: JSON coverage KPIs (no names/CIs).

  PYTHONPATH=scripts .venv/bin/python scripts/titular_queue.py
  PYTHONPATH=scripts .venv/bin/python scripts/titular_queue.py --next P0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_load import load_env  # noqa: E402
from workbook_enrichment.db import database_url  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
QUEUE_DIR = ROOT / "output" / "persons" / "_queue"
RUNS_DIR = ROOT / "output" / "runs"
PERSONS_DIR = ROOT / "output" / "persons"
IDENTITY_TYPES = (
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
)
_CEDULA_NOISE = re.compile(r"cedula|identidad|pasaporte|carnet|rif\b", re.I)


def is_junk_titular(row: dict) -> bool:
    """Drop OCR/date artifacts that look like people but are not."""
    from person_name_gate import is_date_like_identity, is_usable_person_name

    name = (row.get("full_name") or "").strip()
    ci = (row.get("identity_number") or "").strip()
    if is_date_like_identity(ci):
        return True
    if not name:
        return True
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", name):
        return True
    if re.fullmatch(r"\d{5,}", name):
        return True
    if ci and name.replace(" ", "") == ci:
        return True
    if ci and re.fullmatch(r"20\d{6}", ci) and name.startswith(ci):
        return True
    # OCR collage titles dumped as the person name
    if _CEDULA_NOISE.search(name) and len(name.split()) >= 5:
        return True
    if not is_usable_person_name(name):
        return True
    return False


def existing_dossiers() -> set[str]:
    """Map of folder names that already have a README (local dossiers)."""
    found: set[str] = set()
    if not PERSONS_DIR.is_dir():
        return found
    for path in PERSONS_DIR.iterdir():
        if path.name.startswith("_"):
            continue
        if path.is_dir() and (path / "README.md").is_file():
            found.add(path.name)
    return found


def collect_titulares(cur) -> list[dict]:
    cur.execute(
        """
        WITH titular AS (
          SELECT
            p.id::text AS person_id,
            p.full_name,
            p.identity_number,
            p.identity_type::text AS identity_type,
            p.birth_date IS NOT NULL AS has_dob,
            coalesce(p.phone, '') <> '' AS has_phone,
            coalesce(p.address, '') <> '' AS has_address,
            coalesce(p.notes, '') <> '' AS has_notes,
            count(DISTINCT ip.invoice_id)::int AS titular_facts,
            count(DISTINCT bip.person_id) FILTER (
              WHERE bip.person_id IS DISTINCT FROM p.id
            )::int AS beneficiario_people,
            bool_or(
              EXISTS (
                SELECT 1 FROM avila.document d
                WHERE d.invoice_id = ip.invoice_id
                  AND d.document_type::text = ANY(%s)
              )
            ) AS has_id_docs,
            bool_or(ip.source = 'legacy_unknown') AS has_legacy_source,
            bool_or(ip.source IN ('path', 'path_name', 'folder')) AS has_path_source
          FROM avila.invoice_person ip
          JOIN avila.person p ON p.id = ip.person_id
          LEFT JOIN avila.invoice_person bip
            ON bip.invoice_id = ip.invoice_id AND bip.role = 'beneficiario'
          WHERE ip.role = 'titular'
          GROUP BY p.id
        )
        SELECT * FROM titular
        ORDER BY titular_facts DESC, full_name
        """,
        (list(IDENTITY_TYPES),),
    )
    return [dict(r) for r in cur.fetchall()]


def assign_cohort(row: dict) -> str:
    has_ci = bool(row.get("identity_number"))
    has_ben = (row.get("beneficiario_people") or 0) > 0
    missing_contact = not row.get("has_dob") or not row.get("has_phone")

    if has_ci and has_ben and missing_contact:
        return "P0"
    if has_ci and not has_ben and missing_contact:
        return "P1"
    if (not has_ci) and row.get("has_id_docs"):
        return "P2"
    if not has_ci:
        return "P3"
    # CI present, contact mostly filled
    if missing_contact:
        return "P1"
    return "P1" if not has_ben else "P0_done_candidate"


def enrich_status(row: dict, dossiers: set[str]) -> dict:
    name = (row.get("full_name") or "").strip()
    cohort = assign_cohort(row)
    junk = is_junk_titular(row)
    # Normalize done-candidate into P0/P1 for queue sorting but mark status
    if junk:
        display_cohort = cohort if cohort != "P0_done_candidate" else "P0"
        status = "junk"
    elif cohort == "P0_done_candidate":
        display_cohort = "P0"
        status = "ready"
    else:
        display_cohort = cohort
        status = "pending"

    if not junk and name in dossiers:
        status = "exported"
        score_path = PERSONS_DIR / name / "completeness.json"
        if score_path.is_file():
            try:
                meta = json.loads(score_path.read_text(encoding="utf-8"))
                row["export_score"] = meta.get("score")
                if (meta.get("score") or 0) >= 80 and not meta.get("open_blocking_reviews"):
                    status = "done"
                elif meta.get("open_blocking_reviews"):
                    status = "blocked"
            except (OSError, json.JSONDecodeError):
                pass

    out = {
        "person_id": row["person_id"],
        "full_name": row.get("full_name"),
        "identity_number": row.get("identity_number"),
        "cohort": display_cohort,
        "raw_cohort": cohort,
        "status": status,
        "titular_facts": row.get("titular_facts") or 0,
        "beneficiario_people": row.get("beneficiario_people") or 0,
        "has_dob": bool(row.get("has_dob")),
        "has_phone": bool(row.get("has_phone")),
        "has_id_docs": bool(row.get("has_id_docs")),
        "export_score": row.get("export_score"),
        "junk": junk,
    }
    return out


def coverage_kpis(rows: list[dict], dossiers: set[str]) -> dict:
    n = len(rows)
    with_ci = sum(1 for r in rows if r.get("identity_number"))
    with_dob = sum(1 for r in rows if r.get("has_dob"))
    with_phone = sum(1 for r in rows if r.get("has_phone"))
    with_ben = sum(1 for r in rows if (r.get("beneficiario_people") or 0) > 0)
    exported = sum(1 for r in rows if (r.get("full_name") or "").strip() in dossiers)
    by_cohort: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in rows:
        by_cohort[r["cohort"]] = by_cohort.get(r["cohort"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "titulares": n,
        "with_ci": with_ci,
        "with_dob": with_dob,
        "with_phone": with_phone,
        "with_beneficiario": with_ben,
        "dossiers_on_disk": len(dossiers),
        "titulares_with_dossier": exported,
        "pct_ci": round(100 * with_ci / n) if n else 0,
        "pct_dob": round(100 * with_dob / n) if n else 0,
        "pct_phone": round(100 * with_phone / n) if n else 0,
        "pct_dossier": round(100 * exported / n) if n else 0,
        "by_cohort": by_cohort,
        "by_status": by_status,
    }


def write_outputs(rows: list[dict], kpis: dict) -> tuple[Path, Path, Path]:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    queue_path = QUEUE_DIR / "queue.jsonl"
    with queue_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Priority order for next picks
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    pending = [
        r
        for r in rows
        if r["status"] in {"pending", "exported", "ready"}
        and r["status"] != "done"
    ]
    pending.sort(
        key=lambda r: (
            order.get(r["cohort"], 9),
            0 if r["status"] == "pending" else 1,
            -(r.get("titular_facts") or 0),
            r.get("full_name") or "",
        )
    )
    next_path = QUEUE_DIR / "next.json"
    next_path.write_text(
        json.dumps({"generated_at": stamp, "next": pending[:20]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    progress = QUEUE_DIR / "progress.md"
    progress.write_text(
        f"""# Titular queue progress

Generated **{stamp}**.

| KPI | Value |
| --- | ---: |
| Titulares | {kpis['titulares']} |
| With CI | {kpis['with_ci']} ({kpis['pct_ci']}%) |
| With DOB | {kpis['with_dob']} ({kpis['pct_dob']}%) |
| With phone | {kpis['with_phone']} ({kpis['pct_phone']}%) |
| With ≥1 beneficiario | {kpis['with_beneficiario']} |
| Dossiers on disk | {kpis['dossiers_on_disk']} |
| Titulares with dossier | {kpis['titulares_with_dossier']} ({kpis['pct_dossier']}%) |

## By cohort

{chr(10).join(f"- **{k}**: {v}" for k, v in sorted(kpis['by_cohort'].items()))}

## By status

{chr(10).join(f"- **{k}**: {v}" for k, v in sorted(kpis['by_status'].items()))}
""",
        encoding="utf-8",
    )

    run_path = RUNS_DIR / f"titular_queue_{stamp}.md"
    run_path.write_text(
        progress.read_text(encoding="utf-8")
        + "\n\nCounts only — queue PHI lives in `output/persons/_queue/queue.jsonl`.\n",
        encoding="utf-8",
    )
    return queue_path, progress, run_path


def pick_next(rows: list[dict], cohort: str | None) -> dict | None:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    candidates = [
        r
        for r in rows
        if r["status"] in {"pending", "ready", "exported"}
        and not r.get("junk")
        and (cohort is None or r["cohort"] == cohort)
    ]
    # Prefer never-exported + missing contact (true P0 work) over already-enriched
    candidates.sort(
        key=lambda r: (
            0 if r["status"] == "pending" else 1,
            0 if (not r.get("has_dob") or not r.get("has_phone")) else 1,
            order.get(r["cohort"], 9),
            -(r.get("titular_facts") or 0),
            r.get("full_name") or "",
        )
    )
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--next",
        nargs="?",
        const="P0",
        default=None,
        metavar="COHORT",
        help="Print the next titular to process (default cohort P0)",
    )
    args = parser.parse_args(argv)
    load_env()

    dossiers = existing_dossiers()
    with psycopg.connect(database_url(), row_factory=dict_row) as conn, conn.cursor() as cur:
        raw = collect_titulares(cur)

    rows = [enrich_status(r, dossiers) for r in raw]
    # Re-map P0_done_candidate cohort label already handled in enrich
    kpis = coverage_kpis(rows, dossiers)
    queue_path, progress_path, run_path = write_outputs(rows, kpis)

    out = {
        "kpis": kpis,
        "queue": str(queue_path.relative_to(ROOT)),
        "progress": str(progress_path.relative_to(ROOT)),
        "run_report": str(run_path.relative_to(ROOT)),
    }
    if args.next is not None:
        nxt = pick_next(rows, args.next if args.next else None)
        if not nxt:
            out["next"] = None
        else:
            out["next"] = {
                "person_id": nxt["person_id"],
                "cohort": nxt["cohort"],
                "status": nxt["status"],
                "titular_facts": nxt["titular_facts"],
                "beneficiario_people": nxt["beneficiario_people"],
                "has_dob": nxt["has_dob"],
                "has_phone": nxt["has_phone"],
                "identity_number": nxt.get("identity_number"),
                "full_name": nxt.get("full_name"),
            }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
