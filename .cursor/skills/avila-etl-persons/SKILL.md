---
name: avila-etl-persons
description: >-
  Resolves Ávila ETL titular/beneficiario roles, identity document classification
  (cédula, carnet, documentos de identificación, acta de nacimiento), person
  upsert/dedupe, OCR reclassify, contact enrichment from packets, and FACT
  path-vs-CI repairs into Neon and private Blob. Use when fixing a person or
  invoice packet, mislabeled identity pages, path patient vs plastic CI
  conflicts, beneficiario/titular navigation, or reclassifying OCR pages.
---

# Ávila ETL persons

Playbook for repairing **people + identity pages + invoice roles** in the Ávila ETL reader. UI branding belongs to `avila-gps-ui`; this skill owns Neon/Blob person graph work only.

## Read first

1. [docs/avila-etl-architecture.md](../../../docs/avila-etl-architecture.md) — schema, document types, enrichment loop.
2. [docs/case-helber-aaron-matheus.md](../../../docs/case-helber-aaron-matheus.md) — worked titular/beneficiario example (PHI; do not copy ids or cédulas into commits or skill notes).
3. This folder: [reference.md](reference.md) (precedence, CLI, SQL) · [examples.md](examples.md) (anonymized walkthrough).

## Hard rules

- Roles live on `avila.invoice_person` (`titular` / `beneficiario` / `unknown`), not as a field on `avila.person`.
- Plastic ID / carnet / ID-collage **CI** → **titular**. A different FACT **path patient name** → **beneficiario**.
- Workbook titular with CI / phone / DOB is protected from weak path overwrites.
- Never promote a CI that only appears **inside an acta de nacimiento** (parents/registrar) to titular.
- Ignore insurer and clinic letterhead phones; only patient-labeled form / domicilio lines enrich `person.phone` / `person.address`.
- Do not commit `Avila-backup/`, identity PNG/PDF crops, or dossier scans under `output/persons/`.
- Prefer `DATABASE_URL_UNPOOLED` for migrations and repair scripts.

## Mandatory workflow (run in order)

When the user names a person, CI, or FACT set — or when identity/role mislabels appear — execute phases 1–8. Skip a phase only when its output already exists and was re-verified this session.

### 1. Discover

- Search `Avila-backup` paths and Neon `avila.person` / `invoice_person` by name and CI.
- Exclude near-miss names (same first name, different surname).
- List candidate FACT numbers and backup paths.

### 2. Inventory

- Create or refresh `output/persons/{NAME}/` with `load-paths.txt` and a page manifest from OCR cache (`output/invoices/ocr/`).
- Classify each page with `scripts/document_types.py` (`classify_document`).
- Note path patient vs any plastic-CI name on the pages.

### 3. People

- Upsert plastic-ID person with `upsert_by_ci` ([scripts/person_upsert.py](../../../scripts/person_upsert.py)).
- Upsert path patient / menor with `upsert_by_name` (`identity_type` unknown when no personal CI).
- Merge same-name provisionals / junk rows via [scripts/cleanup_person_duplicates.py](../../../scripts/cleanup_person_duplicates.py) (`--apply` only after dry-run).

### 4. Load

- If packets are missing from Neon/Blob, load via [scripts/upload_documents_to_blob.py](../../../scripts/upload_documents_to_blob.py) (`BLOB_ACCESS=private`).
- Optional card crops stay as their own `document` rows (`cedula_identidad` / `carnet`), not as a substitute for the collage page type.

### 5. Roles

- Ensure CI person is `titular` on each invoice (`promote_ci_person_as_titular`).
- Link different path name as `beneficiario` (`_link_path_name_as_beneficiario`); set `parentesco` when known (e.g. hijo).
- Confirm one titular per invoice after repair.

### 6. Types

- Reclassify from OCR with [scripts/reclassify_identity_pages.py](../../../scripts/reclassify_identity_pages.py) (dry-run, then `--apply`, scoped `--invoices`).
- Precedence: **acta → collage → carnet → plastic cédula → …** (see [reference.md](reference.md)).
- Ensure enums exist: `sql/004_carnet_document_type.sql`, `sql/005_identity_document_types.sql`.

### 7. Enrich

- From OCR, pull DOB / phone / address for the **person those fields describe**.
- Write to `avila.person`; put uncertain alternate phones in `notes`, not over the primary phone.
- Fix wrong DOB copies (e.g. child DOB on titular) when cédula/acta contradicts Neon.

### 8. Verify

- SQL: role matrix per FACT; document types for identity pages; `person_id` on collage/acta/crops.
- Reader: document Spanish labels; beneficiario profile shows titular banner; titular profile lists beneficiarios.
- Tests: `PYTHONPATH=scripts .venv/bin/python -m unittest test_invoice_rules.DocumentTypeTests test_role_resolution`
- Summarize for the user: what changed, remaining gaps, and dossier path (PHI stays local).

## Stop / escalate

Ask before continuing when:

- Auth workbook rows have no FACT number (`authorization_line.invoice_id` cannot be auto-linked).
- User did not ask to model extra relatives named only on an acta.
- Path CI conflicts with an existing **workbook** titular who has a different CI.
- Multiple plastic CIs on one packet with no clear insured.

## Output expectations

- Prefer repairing data + classification over one-off notes text.
- Update or add a short case note under `output/persons/{NAME}/` when doing a full repair; keep scans untracked.
- Do not invent a personal CI for a menor; acta is identity proof.
