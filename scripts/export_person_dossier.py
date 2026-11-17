#!/usr/bin/env python3
"""Export a full per-person dossier under output/persons/{NAME}/ (git-ignored).

Read-only against Neon unless --copy-pages also writes local page copies.
No PHI is printed; only the dossier path and completeness score go to stdout.

  PYTHONPATH=scripts .venv/bin/python scripts/export_person_dossier.py --ci 19610384
  PYTHONPATH=scripts .venv/bin/python scripts/export_person_dossier.py --person-id UUID
  PYTHONPATH=scripts .venv/bin/python scripts/export_person_dossier.py --name "JUAN PEREZ"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import classify_document  # noqa: E402
from env_load import load_env  # noqa: E402
from ocr_invoice_pages import _read_cache  # noqa: E402
from person_upsert import fold_person_name  # noqa: E402
from workbook_enrichment.db import database_url  # noqa: E402
from workbook_enrichment.discover import BACKUP, iter_normalized_rows, iter_workbook_paths  # noqa: E402
from workbook_enrichment.canonical import guess_family  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PERSONS_DIR = ROOT / "output" / "persons"
IDENTITY_TYPES = {
    "cedula_identidad",
    "carnet",
    "documentos_identificacion",
    "pasaporte",
    "acta_nacimiento",
}
BLOCKING_REVIEW_KINDS = {"ci_conflict", "multiple_ci", "dob_conflict", "workbook_titular"}

PERSON_FIELDS = [
    "id",
    "full_name",
    "identity_type",
    "identity_number",
    "birth_date",
    "phone",
    "address",
    "notes",
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, memoryview):
        return bytes(value).hex()
    return value


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(",".join(fieldnames or ["id"]) + "\n", encoding="utf-8")
        return
    fields = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _jsonable(row.get(k)) for k in fields})


def _ocr_text_from_cache(backup_path: str | None) -> tuple[str, bool]:
    if not backup_path:
        return "", False
    record = _read_cache(backup_path)
    if not record:
        return "", False
    pages = record.get("pages") or []
    parts: list[str] = []
    for page in pages:
        if isinstance(page, dict):
            parts.append(page.get("text") or "")
        elif isinstance(page, str):
            parts.append(page)
    if not parts and isinstance(record.get("text"), str):
        parts.append(record["text"])
    text = "\n".join(parts)
    return text, True


def _ocr_digest(text: str, n: int = 24) -> str:
    if not text.strip():
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def resolve_person(cur, *, person_id: str | None, ci: str | None, name: str | None) -> dict:
    if person_id:
        cur.execute(
            """
            SELECT id::text AS id, full_name, identity_type::text AS identity_type,
                   identity_number, birth_date, phone, address, notes
            FROM avila.person WHERE id = %s::uuid
            """,
            (person_id,),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"person not found: {person_id}")
        return dict(row)

    if ci:
        digits = re.sub(r"\D", "", ci)
        cur.execute(
            """
            SELECT id::text AS id, full_name, identity_type::text AS identity_type,
                   identity_number, birth_date, phone, address, notes
            FROM avila.person WHERE identity_number = %s
            """,
            (digits,),
        )
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"person not found for CI {digits}")
        return dict(row)

    if name:
        folded = fold_person_name(name)
        cur.execute(
            """
            SELECT id::text AS id, full_name, identity_type::text AS identity_type,
                   identity_number, birth_date, phone, address, notes
            FROM avila.person
            WHERE name_folded = %s OR lower(full_name) = lower(%s)
            ORDER BY identity_number NULLS LAST
            LIMIT 5
            """,
            (folded, name.strip()),
        )
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            raise SystemExit(f"person not found for name {name!r}")
        if len(rows) > 1:
            ids = ", ".join(r["id"][:8] for r in rows)
            raise SystemExit(f"ambiguous name {name!r}; pass --person-id ({ids}…)")
        return rows[0]

    raise SystemExit("pass --ci, --person-id, or --name")


def fetch_invoices(cur, person_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT i.invoice_number, i.control_number, i.issue_date, i.total_bs, i.total_usd,
               i.clave, a.code AS account, ip.role::text AS role, ip.parentesco, ip.source,
               i.year, i.month, i.lote, i.channel, i.id::text AS invoice_id
        FROM avila.invoice_person ip
        JOIN avila.invoice i ON i.id = ip.invoice_id
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE ip.person_id = %s::uuid
        ORDER BY i.invoice_number
        """,
        (person_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_role_graph(cur, person_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT i.invoice_number, p.full_name, p.identity_number,
               ip.role::text AS role, ip.parentesco, ip.source
        FROM avila.invoice_person ip
        JOIN avila.invoice i ON i.id = ip.invoice_id
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id IN (
          SELECT invoice_id FROM avila.invoice_person WHERE person_id = %s::uuid
        )
        ORDER BY i.invoice_number, ip.role, p.full_name
        """,
        (person_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_documents(cur, person_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT i.invoice_number, d.id::text AS document_id, d.page_index,
               d.document_type::text AS document_type, d.evidence,
               d.upload_status::text AS upload_status, d.blob_pathname,
               d.person_id::text AS person_id, d.sha256,
               sf.backup_path, sf.file_label, sf.rule_id, sf.pages AS source_pages
        FROM avila.document d
        JOIN avila.invoice i ON i.id = d.invoice_id
        LEFT JOIN avila.source_file sf ON sf.id = d.source_file_id
        WHERE d.invoice_id IN (
          SELECT invoice_id FROM avila.invoice_person WHERE person_id = %s::uuid
        )
        ORDER BY i.invoice_number, coalesce(d.page_index, 0), sf.backup_path NULLS LAST
        """,
        (person_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_auth_lines(cur, person_id: str, claves: list[str]) -> list[dict]:
    cur.execute(
        """
        SELECT id::text AS id, clave_rms, contratante, service_date, request_date,
               diagnosis, service_description, provider_name, amount_bs, amount_usd,
               coverage_amount, authorized_amount,
               invoice_id::text AS invoice_id, person_id::text AS person_id
        FROM avila.authorization_line
        WHERE person_id = %s::uuid
           OR (cardinality(%s::text[]) > 0 AND clave_rms = ANY(%s::text[]))
        ORDER BY coalesce(service_date, request_date) DESC NULLS LAST
        """,
        (person_id, claves, claves),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_reviews(cur, person_id: str) -> list[dict]:
    cur.execute(
        """
        SELECT kind, status, evidence::text AS evidence,
               document_id::text AS document_id, resolved_by,
               resolved_at::text AS resolved_at, created_at::text AS created_at
        FROM avila.review_item
        WHERE person_id = %s::uuid
        ORDER BY created_at
        """,
        (person_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_provenance(cur, person_id: str, document_ids: list[str]) -> list[dict]:
    entity_ids = [person_id, *document_ids]
    cur.execute(
        """
        SELECT entity, field, rule_id, source_kind,
               left(source_ref, 120) AS source_ref, created_at::text AS created_at
        FROM avila.field_provenance
        WHERE entity_id = ANY(%s)
        ORDER BY created_at DESC
        LIMIT 80
        """,
        (entity_ids,),
    )
    return [dict(r) for r in cur.fetchall()]


def scan_workbook_rows(*, ci: str | None, full_name: str | None, limit: int = 40) -> list[dict]:
    """Scan Avila-backup sabana/relación workbooks for matching CI or name."""
    if not BACKUP.is_dir():
        return []
    ci_digits = re.sub(r"\D", "", ci or "")
    name_folded = fold_person_name(full_name or "") if full_name else ""
    hits: list[dict] = []
    for path in iter_workbook_paths(BACKUP):
        relative = str(path.relative_to(BACKUP))
        family = guess_family(relative, [])
        if family not in {"sabana", "relacion", "amp"}:
            continue
        try:
            for sheet, row_number, row in iter_normalized_rows(path, relative):
                t_ci = re.sub(r"\D", "", str(row.get("titular_ci") or ""))
                b_ci = re.sub(r"\D", "", str(row.get("beneficiario_ci") or ""))
                t_name = fold_person_name(str(row.get("titular_name") or ""))
                b_name = fold_person_name(str(row.get("beneficiario_name") or ""))
                match = False
                if ci_digits and ci_digits in {t_ci, b_ci}:
                    match = True
                elif name_folded and name_folded in {t_name, b_name}:
                    match = True
                if not match:
                    continue
                flat = {k: row.get(k) for k in sorted(row.keys())}
                flat.update(
                    {
                        "workbook": relative,
                        "sheet": sheet,
                        "row": row_number,
                    }
                )
                hits.append(flat)
                if len(hits) >= limit:
                    return hits
        except Exception:  # noqa: BLE001 — skip unreadable workbooks
            continue
    return hits


def build_page_analysis(
    docs: list[dict],
    out_dir: Path,
    *,
    copy_pages: bool,
) -> tuple[list[dict], list[dict]]:
    """Return (page_analysis rows, page_manifest rows)."""
    pages_dir = out_dir / "pages"
    if copy_pages:
        pages_dir.mkdir(parents=True, exist_ok=True)

    analysis: list[dict] = []
    manifest: list[dict] = []
    for doc in docs:
        backup = doc.get("backup_path") or ""
        text, hit = _ocr_text_from_cache(backup)
        flat = re.sub(r"\s+", " ", text).strip()
        classified_type, classified_ev = classify_document(text, backup_path=backup)
        neon_type = doc.get("document_type") or ""
        copied = False
        nbytes = 0
        if copy_pages and backup:
            src = BACKUP / backup
            if src.is_file():
                safe_inv = str(doc.get("invoice_number") or "FACT")
                safe_type = neon_type or classified_type or "page"
                stem = Path(backup).stem
                dest = pages_dir / f"FACT {safe_inv} - {safe_type} - {stem}{src.suffix}"
                try:
                    shutil.copy2(src, dest)
                    copied = True
                    nbytes = dest.stat().st_size
                except OSError:
                    copied = False

        analysis.append(
            {
                "invoice": doc.get("invoice_number"),
                "type": neon_type or classified_type,
                "evidence": doc.get("evidence") or classified_ev,
                "path": backup,
                "ocr_len": len(text),
                "ocr_head": flat[:400],
                "copied": copied,
                "bytes": nbytes,
                "ocr_digest": _ocr_digest(text),
                "ocr_hit": hit,
                "classified_type": classified_type,
                "person_id": doc.get("person_id"),
            }
        )
        manifest.append(
            {
                "backup_path": backup,
                "page_index": doc.get("page_index"),
                "document_type": neon_type,
                "evidence": doc.get("evidence"),
                "person_guess": "",
                "identity_number": "",
                "invoice_pages_label": doc.get("file_label") or "",
                "ocr_cached": "yes" if hit else "no",
                "notes": classified_type if classified_type != neon_type else "",
            }
        )
    return analysis, manifest


def completeness_score(
    person: dict,
    invoices: list[dict],
    roles: list[dict],
    docs: list[dict],
    auth: list[dict],
    reviews: list[dict],
    workbook_rows: list[dict],
) -> tuple[int, list[str], dict[str, int]]:
    """Return (score 0-100, gaps, breakdown)."""
    gaps: list[str] = []
    parts: dict[str, int] = {}

    # Identity (40)
    identity = 0
    if person.get("identity_number"):
        identity += 15
    else:
        gaps.append("missing CI")
    if person.get("full_name"):
        identity += 5
    else:
        gaps.append("missing name")
    if person.get("birth_date"):
        identity += 10
    else:
        gaps.append("missing DOB")
    if person.get("phone"):
        identity += 5
    else:
        gaps.append("missing phone")
    if person.get("address") or (person.get("notes") or "").strip():
        identity += 5
    else:
        gaps.append("missing address/notes")
    parts["identity"] = identity

    # Graph (25)
    graph = 0
    titular_facts = [r for r in invoices if r.get("role") == "titular"]
    if titular_facts:
        graph += 15
    else:
        gaps.append("no titular FACT link")
    ben_on_facts = [
        r
        for r in roles
        if r.get("role") == "beneficiario"
        and r.get("identity_number") != person.get("identity_number")
    ]
    if ben_on_facts:
        graph += 10
    elif workbook_rows:
        # workbook says there should be a dependent but Neon graph empty
        gaps.append("workbook hit but no beneficiario on FACT")
    else:
        # self-insured is fine — award partial credit
        graph += 5
        gaps.append("no beneficiario (self-visit ok if expected)")
    parts["graph"] = graph

    # Packets (20)
    packets = 0
    if docs:
        packets += 10
    else:
        gaps.append("no documents on linked invoices")
    id_docs = [d for d in docs if (d.get("document_type") or "") in IDENTITY_TYPES]
    id_linked = [d for d in id_docs if d.get("person_id") == person.get("id")]
    if id_docs and id_linked:
        packets += 10
    elif id_docs:
        packets += 4
        gaps.append("identity pages not linked to person_id")
    else:
        gaps.append("no identity document pages")
    parts["packets"] = packets

    # Workbook / auth (10)
    wb = 0
    if workbook_rows:
        wb += 6
    else:
        gaps.append("no workbook rows (or --workbook not run)")
    if auth:
        wb += 4
    else:
        gaps.append("no authorization_line rows")
    parts["workbook_auth"] = wb

    # Reviews (5)
    open_blocking = [
        r
        for r in reviews
        if r.get("status") == "open" and r.get("kind") in BLOCKING_REVIEW_KINDS
    ]
    reviews_score = 0 if open_blocking else 5
    if open_blocking:
        kinds = sorted({r["kind"] for r in open_blocking})
        gaps.append("open blocking reviews: " + ", ".join(kinds))
    parts["reviews"] = reviews_score

    total = sum(parts.values())
    return total, gaps, parts


def render_readme(
    person: dict,
    invoices: list[dict],
    roles: list[dict],
    docs: list[dict],
    auth: list[dict],
    reviews: list[dict],
    workbook_rows: list[dict],
    score: int,
    gaps: list[str],
    parts: dict[str, int],
) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    titular_inv = [i for i in invoices if i.get("role") == "titular"]
    ben_people = {}
    for r in roles:
        if r.get("role") != "beneficiario":
            continue
        if r.get("identity_number") and r.get("identity_number") == person.get("identity_number"):
            continue
        if r.get("full_name") == person.get("full_name"):
            continue
        key = r.get("identity_number") or r.get("full_name")
        ben_people[key] = r

    inv_lines = []
    for inv in titular_inv:
        inv_lines.append(
            f"| **{inv.get('invoice_number')}** | {inv.get('control_number') or '—'} | "
            f"{inv.get('issue_date') or '—'} | {inv.get('clave') or '—'} | "
            f"{inv.get('account') or '—'} | {inv.get('source') or '—'} |"
        )
    if not inv_lines:
        inv_lines.append("| — | — | — | — | — | — |")

    ben_lines = []
    for r in ben_people.values():
        ben_lines.append(
            f"| {r.get('full_name')} | {r.get('identity_number') or '—'} | "
            f"{r.get('parentesco') or '—'} | {r.get('source') or '—'} |"
        )
    if not ben_lines:
        ben_lines.append("| — | — | — | — |")

    gap_bullets = "\n".join(f"- {g}" for g in gaps) if gaps else "- None recorded."
    open_revs = [r for r in reviews if r.get("status") == "open"]
    rev_note = f"{len(open_revs)} open" if open_revs else "none open"

    return f"""# {person.get('full_name') or '(sin nombre)'} — dossier

Updated **{today}** via `export_person_dossier.py`. Copies and Neon exports; originals stay in `Avila-backup`.

## Completeness

**Score: {score}/100** — identity {parts.get('identity', 0)}, graph {parts.get('graph', 0)}, packets {parts.get('packets', 0)}, workbook/auth {parts.get('workbook_auth', 0)}, reviews {parts.get('reviews', 0)}.

## Persona (Neon)

| Field | Value |
| --- | --- |
| Full name | {person.get('full_name') or '—'} |
| Cédula | {person.get('identity_number') or '—'} ({person.get('identity_type') or '—'}) |
| Birth date | {person.get('birth_date') or '—'} |
| Phone | {person.get('phone') or '—'} |
| Address | {person.get('address') or '—'} |
| Notes | {(person.get('notes') or '—')[:240]} |
| Neon id | `{person.get('id')}` |

## Beneficiarios (on shared FACTs)

| Name | CI | Parentesco | Source |
| --- | --- | --- | --- |
{chr(10).join(ben_lines)}

## Invoices (role on this person)

| FACT | Control | Emisión | Clave | Account | Source |
| --- | --- | --- | --- | --- | --- |
{chr(10).join(inv_lines)}

Documents linked: **{len(docs)}**. Authorization lines: **{len(auth)}**. Workbook rows: **{len(workbook_rows)}**. Reviews: **{rev_note}**.

## Gaps

{gap_bullets}

## Artifacts

- `neon-person.csv`, `neon-invoices.csv`, `neon-beneficiarios.csv`, `neon-documents.csv`
- `neon-authorization-lines.csv`, `neon-provenance.csv`, `neon-review-items.csv`
- `workbook-rows.csv`, `load-paths.txt`, `page-manifest.csv`, `page-analysis.json`
- `pages/` when `--copy-pages` was used
"""


def export_dossier(
    *,
    person_id: str | None = None,
    ci: str | None = None,
    name: str | None = None,
    copy_pages: bool = False,
    workbook: bool = False,
    out_root: Path | None = None,
) -> dict:
    url = database_url()
    root = out_root or PERSONS_DIR
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        person = resolve_person(cur, person_id=person_id, ci=ci, name=name)
        pid = person["id"]
        invoices = fetch_invoices(cur, pid)
        roles = fetch_role_graph(cur, pid)
        docs = fetch_documents(cur, pid)
        claves = [str(i["clave"]) for i in invoices if i.get("clave")]
        auth = fetch_auth_lines(cur, pid, claves)
        reviews = fetch_reviews(cur, pid)
        doc_ids = [d["document_id"] for d in docs if d.get("document_id")]
        provenance = fetch_provenance(cur, pid, doc_ids)

    folder_name = (person.get("full_name") or f"person-{pid[:8]}").strip()
    out_dir = root / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    workbook_rows: list[dict] = []
    if workbook:
        workbook_rows = scan_workbook_rows(
            ci=person.get("identity_number"),
            full_name=person.get("full_name"),
        )
    elif (out_dir / "workbook-rows.csv").is_file():
        # Keep prior workbook export if present and --workbook not requested.
        with (out_dir / "workbook-rows.csv").open(encoding="utf-8") as handle:
            workbook_rows = list(csv.DictReader(handle))

    # Neon CSVs (drop internal invoice_id from invoices export for stable columns)
    inv_export = [
        {k: v for k, v in row.items() if k != "invoice_id"} for row in invoices
    ]
    _write_csv(out_dir / "neon-person.csv", [person], PERSON_FIELDS)
    _write_csv(
        out_dir / "neon-invoices.csv",
        inv_export,
        [
            "invoice_number",
            "control_number",
            "issue_date",
            "total_bs",
            "total_usd",
            "clave",
            "account",
            "role",
            "parentesco",
            "source",
            "year",
            "month",
            "lote",
            "channel",
        ],
    )
    _write_csv(
        out_dir / "neon-beneficiarios.csv",
        roles,
        ["invoice_number", "full_name", "identity_number", "role", "parentesco", "source"],
    )
    doc_export = [
        {
            "invoice_number": d.get("invoice_number"),
            "document_type": d.get("document_type"),
            "evidence": d.get("evidence"),
            "upload_status": d.get("upload_status"),
            "blob_pathname": d.get("blob_pathname"),
            "backup_path": d.get("backup_path"),
            "page_index": d.get("page_index"),
            "person_id": d.get("person_id"),
            "document_id": d.get("document_id"),
            "sha256": d.get("sha256"),
            "file_label": d.get("file_label"),
            "rule_id": d.get("rule_id"),
            "source_pages": d.get("source_pages"),
        }
        for d in docs
    ]
    _write_csv(out_dir / "neon-documents.csv", doc_export)
    _write_csv(out_dir / "neon-authorization-lines.csv", auth)
    _write_csv(out_dir / "neon-review-items.csv", reviews, ["kind", "status", "evidence", "document_id", "resolved_by", "resolved_at", "created_at"])
    _write_csv(out_dir / "neon-provenance.csv", provenance)
    if workbook_rows:
        # Prefer stable column order when possible
        keys: list[str] = []
        for row in workbook_rows:
            for k in row:
                if k not in keys:
                    keys.append(k)
        _write_csv(out_dir / "workbook-rows.csv", workbook_rows, keys)
    elif not (out_dir / "workbook-rows.csv").is_file():
        _write_csv(out_dir / "workbook-rows.csv", [], ["workbook", "sheet", "row"])

    paths = sorted(
        {d.get("backup_path") for d in docs if d.get("backup_path")}
        | {d.get("backup_path") for d in docs if d.get("file_label") == "invoice_packet" and d.get("backup_path")}
    )
    # Prefer unique source packet roots for load-paths when available
    load_paths = sorted({p for p in paths if p})
    (out_dir / "load-paths.txt").write_text(
        "\n".join(load_paths) + ("\n" if load_paths else ""),
        encoding="utf-8",
    )

    analysis, manifest = build_page_analysis(docs, out_dir, copy_pages=copy_pages)
    (out_dir / "page-analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(
        out_dir / "page-manifest.csv",
        manifest,
        [
            "backup_path",
            "page_index",
            "document_type",
            "evidence",
            "person_guess",
            "identity_number",
            "invoice_pages_label",
            "ocr_cached",
            "notes",
        ],
    )

    score, gaps, parts = completeness_score(
        person, invoices, roles, docs, auth, reviews, workbook_rows
    )
    readme = render_readme(
        person, invoices, roles, docs, auth, reviews, workbook_rows, score, gaps, parts
    )
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    if not (out_dir / "case-notes.md").is_file():
        (out_dir / "case-notes.md").write_text(
            f"# Case notes — {person.get('full_name')}\n\n"
            f"Created by export_person_dossier on {datetime.now(timezone.utc).date().isoformat()}.\n"
            f"Neon id `{pid}`.\n",
            encoding="utf-8",
        )

    try:
        dossier_rel = str(out_dir.relative_to(ROOT))
    except ValueError:
        dossier_rel = str(out_dir)
    meta = {
        "person_id": pid,
        "full_name": person.get("full_name"),
        "identity_number": person.get("identity_number"),
        "dossier": dossier_rel,
        "score": score,
        "gaps": gaps,
        "parts": parts,
        "invoices": len(invoices),
        "documents": len(docs),
        "beneficiarios": len(
            {
                r.get("identity_number") or r.get("full_name")
                for r in roles
                if r.get("role") == "beneficiario"
                and r.get("identity_number") != person.get("identity_number")
            }
        ),
        "auth_lines": len(auth),
        "workbook_rows": len(workbook_rows),
        "open_blocking_reviews": sum(
            1
            for r in reviews
            if r.get("status") == "open" and r.get("kind") in BLOCKING_REVIEW_KINDS
        ),
    }
    (out_dir / "completeness.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", help="Cédula digits (or V-prefixed)")
    parser.add_argument("--person-id", help="avila.person UUID")
    parser.add_argument("--name", help="Exact / folded full name (must be unique)")
    parser.add_argument(
        "--copy-pages",
        action="store_true",
        help="Copy backup pages into dossier pages/ (PHI; git-ignored)",
    )
    parser.add_argument(
        "--workbook",
        action="store_true",
        help="Scan Avila-backup sabana/relación workbooks for matching CI/name",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="Override output/persons root (tests)",
    )
    args = parser.parse_args(argv)

    # Ensure env is loaded for DATABASE_URL_UNPOOLED
    load_env()
    meta = export_dossier(
        person_id=args.person_id,
        ci=args.ci,
        name=args.name,
        copy_pages=args.copy_pages,
        workbook=args.workbook,
        out_root=args.out_root,
    )
    # Counts only — no PHI on stdout beyond folder relative path already local
    print(
        json.dumps(
            {
                "dossier": meta["dossier"],
                "score": meta["score"],
                "invoices": meta["invoices"],
                "documents": meta["documents"],
                "beneficiarios": meta["beneficiarios"],
                "auth_lines": meta["auth_lines"],
                "workbook_rows": meta["workbook_rows"],
                "gaps": meta["gaps"],
                "person_id_prefix": (meta["person_id"] or "")[:8],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
