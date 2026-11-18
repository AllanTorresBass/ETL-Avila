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
2. [docs/case-titular-beneficiario.md](../../../docs/case-titular-beneficiario.md) — anonymized worked titular/beneficiario example. Real names/ids for a case live only in the git-ignored dossier `output/persons/{NAME}/case-notes.md`.
3. This folder: [reference.md](reference.md) (precedence, CLI, SQL) · [examples.md](examples.md) (anonymized walkthrough).

## Hard rules

- Roles live on `avila.invoice_person` (`titular` / `beneficiario` / `unknown`), not as a field on `avila.person`.
- Plastic ID / carnet / ID-collage **CI** → **titular**. A different FACT **path patient name** → **beneficiario**.
- Workbook titular with CI / phone / DOB is protected from weak path overwrites.
- Never promote a CI that only appears **inside an acta de nacimiento** (parents/registrar) to titular.
- A **RIF is never a person**: identity pages only yield a cédula/pasaporte (`extract_personal_identity`, `identity_page_ci`).
- Every CI → titular change goes through **`try_promote_ci_titular`** (workbook + CI-conflict guard). Never call `promote_ci_person_as_titular` directly from new code.
- Ignore insurer and clinic letterhead phones; only patient-labeled form / domicilio lines enrich `person.phone` / `person.address`.
- Do not commit `Avila-backup/`, `output/persons/`, `scripts/local_cases/`, `output/invoices/invoices.csv` / `invoice-pages.csv` (all git-ignored). No real names, cédulas, phones or Neon person ids in tracked files, tests or commit messages — use fakes (`JUAN PEREZ`, `11222333`).
- Prefer `DATABASE_URL_UNPOOLED` for migrations and repair scripts.
- **Provenance is required.** Every apply script calls `provenance.start_run` / `finish_run`, and every person, role, document-type or invoice field change goes through `provenance.record` (value hashes only) inside a `provenance.source(kind, ref)` block. `invoice_person.source` must be one of the closed vocabulary values; never write free text.
- When a script is unsure, open a `review_item` (`provenance.open_review`) instead of guessing. Staff resolve it in the reader at `/revision`.
- Person DOB is fill-only. A different DOB from another source opens `dob_conflict`; it never overwrites.
- Merges go through `merge_person` (or the `/revision` Aceptar action). Two different cédulas are never merged.
- An "auto-review rejected" `--apply` can still have run. Check `avila.etl_run` and `ps` before rerunning, so you don't apply twice.

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
- Spelling variants (Josues/Josuas, Gonzales/Gonzalez): run [scripts/identity_resolver.py](../../../scripts/identity_resolver.py) dry-run, inspect the counts, then `--apply`. Only equal-DOB high scores auto-merge; the rest become `duplicate_candidate` reviews.

### 4. Load

- If packets are missing from Neon/Blob, load via [scripts/upload_documents_to_blob.py](../../../scripts/upload_documents_to_blob.py) (`BLOB_ACCESS=private`).
- If the person's FACT only exists in a scanner lot (`rule_id = scan_outside_invoice`, mostly Seguros Miranda), OCR the folder with `ocr_invoice_pages.py --scope scan --folder …`, segment it with `segment_scan_packets.py --folder …`, then load with `upload_documents_to_blob.py --scan-packets`. See the scanner section in [reference.md](reference.md).
- Fill fiscal fields and fiscal roles with `fiscal_extract.py --apply --link-roles`, then link authorization lines with `match_auth_lines.py` (dry-run first).
- Optional card crops stay as their own `document` rows (`cedula_identidad` / `carnet`), not as a substitute for the collage page type.

### 5. Roles

- Measure gaps with `role_inventory.py`, then fill titulares via `fiscal_extract.py --missing-titular --roles-only --link-roles` and identity pages via `repair_corpus_person_roles.py`.
- Harvest / propagate beneficiarios with `role_linkage.py` (`beneficiario`, `propagate`, `workbook`, or `all`).
- Ensure CI person is `titular` on each invoice via `try_promote_ci_titular` (it links the different path name as `beneficiario` too).
- Any outcome other than `promoted` (`workbook_titular`, `ci_conflict`) or a `multiple_ci` page is a **review item** — see Stop / escalate.
- Set `parentesco` when known (e.g. hijo).
- Confirm one titular per invoice after repair.

### 6. Types

- Reclassify from OCR with [scripts/reclassify_identity_pages.py](../../../scripts/reclassify_identity_pages.py) (dry-run, then `--apply`; `--invoices` or `--all` is required). Pages that move from an ID type to `acta_nacimiento` demote a titular that only came from that page to `unknown`.
- Precedence: **acta → collage → carnet → plastic cédula → comprobante/siniestro → pasaporte → …** (see [reference.md](reference.md)).
- Ensure enums exist: `sql/004_carnet_document_type.sql`, `sql/005_identity_document_types.sql`.

### 7. Enrich

- Corpus fill is `repair_workbook_contact.py` then `enrich_person_contact.py` (dry-run, then `--apply`). Do not copy a titular phone or address onto a minor.
- From OCR, pull DOB / phone / address for the **person those fields describe**. Cédula date stays with that cédula. Acta date stays with the child. Acta domicilio stays with the titular. Clinic and insurer numbers are not patient phones.
- Write to `avila.person`; put a clearly weaker second phone in `notes`, not over the primary phone. Two competing values open `dob_conflict`, `phone_conflict`, or `address_conflict` and do not overwrite.
- Every person gets `avila.person.contact_gap` with a closed code per field (`filled`, `not_applicable_menor`, `no_candidate_page`, `ocr_no_cue`, `unparsed`, `only_letterhead`, `ambiguous`, `conflict`, `blocked_review`, `junk`, `no_invoice_documents`, `unsegmented_scan`, `outside_ocr_scope`). The profile shows the Spanish sentence. Counts-only report: `output/runs/{run_id}.md`. Hashes and paths: `output/persons/_queue/contact-gaps.jsonl` (git-ignored).
- Fix wrong DOB copies (e.g. child DOB on titular) when cédula/acta contradicts Neon.

### 8. Verify

- SQL: role matrix per FACT; document types for identity pages; `person_id` on collage/acta/crops; open `review_item` rows for the person.
- Reader: document Spanish labels; beneficiario profile shows titular banner; titular profile lists beneficiarios; **Historial** shows each change with its source and rule.
- Run report: counters in `output/runs/{run_id}.md` (and `avila.etl_run.counters`) match what you expected.
- Tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .venv/bin/python -m unittest discover -s scripts -p 'test_*.py'` (includes `test_golden_packets`: titular + minor + acta, collage noise, claim form, spelling variant).
- Summarize for the user: what changed, remaining gaps, and dossier path (PHI stays local).

## Stop / escalate

Ask before continuing when:

- Auth workbook rows have no FACT number and `match_auth_lines.py` leaves them unlinked or as `auth_match` reviews.
- User did not ask to model extra relatives named only on an acta.
- Path CI conflicts with an existing **workbook** titular who has a different CI.
- Multiple plastic CIs on one packet with no clear insured (scripts report `multiple_ci`; the current titular's CI among them counts as clear).
- A script reports `workbook_titular` / `ci_conflict` / `titular came from an acta page`.

## Titular Completeness (one-by-one dossiers)

Goal: for **each titular**, assemble the whole information set into `output/persons/{NAME}/` (git-ignored) and close safe Neon gaps — same depth as Anayrely, not just bulk role links.

### Queue

```bash
PYTHONPATH=scripts .venv/bin/python scripts/titular_queue.py
PYTHONPATH=scripts .venv/bin/python scripts/titular_queue.py --next P0
```

Cohorts: **P0** CI + beneficiario + missing DOB/phone → **P1** CI self-only missing contact → **P2** ID docs but empty CI → **P3** name-only. Progress (counts only) in `output/persons/_queue/progress.md`; full queue PHI in `queue.jsonl`.

### Export

```bash
PYTHONPATH=scripts .venv/bin/python scripts/export_person_dossier.py --ci 19610384
# or --person-id UUID | --name "…"
# optional: --copy-pages  --workbook
```

Writes README + completeness score, Neon CSVs, `page-analysis.json`, `page-manifest.csv`, `load-paths.txt`, `case-notes.md`. Pure export is read-only on Neon.

### Serial loop (one titular fully before the next)

1. `titular_queue.py --next P0` → pick person.
2. `export_person_dossier.py` baseline.
3. Gap-detect from score / README Gaps.
4. Repair only what is missing (phases 3–8 above).
5. Re-export; mark queue status via re-running `titular_queue.py` (`done` when score ≥ 80 and no blocking reviews).
6. `local_cases/` only when parameterized repair cannot express the edge.

Do not parallelize PHI-heavy crop/vision without a human gate. Blockers (`ci_conflict`, `multiple_ci`, `dob_conflict`, `workbook_titular`) stop automation for that person until `/revision` accept.

## Output expectations

- Prefer repairing data + classification over one-off notes text.
- Update or add `output/persons/{NAME}/case-notes.md` when doing a full repair (ignored by git). Generalizable lessons go into the anonymized docs, never the real values.
- Case-specific one-off scripts go in `scripts/local_cases/` (ignored), not `scripts/`.
- Do not invent a personal CI for a menor; acta is identity proof.
- Prefer `export_person_dossier.py` over ad-hoc chat dumps for Neon CSVs / page-analysis.
