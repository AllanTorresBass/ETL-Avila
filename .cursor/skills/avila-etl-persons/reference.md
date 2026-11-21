# Ávila ETL persons — reference

Dense lookup for [SKILL.md](SKILL.md). No patient PHI in this file.

## Document-type precedence

`classify_document` in [scripts/document_types.py](../../../scripts/document_types.py) must resolve in this order after fiscal / unreadable:

| Order | Type code | Spanish label | Win when |
| ---: | --- | --- | --- |
| 1 | `acta_nacimiento` | Acta de nacimiento | Acta de nacimiento, acta N°, comisión / unidad de registro civil, presentación del nacido; bare “registro civil” only with acta / presentante / folio / libro |
| 2 | `documentos_identificacion` | Documentos de identificación | GPS cover `DOCUMENTOS DE IDENTIFICACION` (cédula + carnet collage) |
| 3 | `carnet` | Carnet | BDV / employer badge cues without dominating plastic cédula title |
| 4 | `cedula_identidad` | Cédula de identidad | `CEDULA DE IDENTIDAD` + card fields; not forms or actas |
| 5 | `comprobante` | Comprobante | Incl. declaración de siniestro / planilla / reclamo letters (`claim_form`; wins over the “C.I. o PASAPORTE” label and the printed “FACTURA N°” box) |
| 6 | `pasaporte` | Pasaporte | Passport card; never forms, fiscal “C.I., R.I.F. o PASAPORTE”, or “C.I. o PASAPORTE” labels |
| 7 | clinical / path | egreso, ingreso, informe, lab, … | Path or OCR clinical tokens. A patient report (NOMBRE DEL PACIENTE + DIAGNÓSTICO) is `informe_medico` even with an APS footer, unless titled as an order |
| 8 | `carta_aval` (folder) | Carta aval | Only when no OCR rule matched and the path is under a `CARTA AVAL` folder |
| 9 | `otro_anexo` | Otro anexo | Residual |

A plastic cédula plus a BDV carnet on one page with no collage title is still `documentos_identificacion` (evidence `collage_untitled`). A solicitud de carta aval that mentions “carnet” in its checklist is `carta_aval`, not `carnet`.

Migrations: [sql/004_carnet_document_type.sql](../../../sql/004_carnet_document_type.sql), [sql/005_identity_document_types.sql](../../../sql/005_identity_document_types.sql).

Loader identity linking ([scripts/upload_documents_to_blob.py](../../../scripts/upload_documents_to_blob.py)):

- `CI_TITULAR_TYPES` (`cedula_identidad` / `pasaporte` / `carnet` / `documentos_identificacion`) → `identity_page_ci` picks one personal CI (never a RIF; dotted `12.345.678` ok) → `upsert_by_ci` with the cédula OCR name → `try_promote_ci_titular` (guarded) → path name → beneficiario when different. Blocked / multiple → printed `titular review` line, roles untouched.
- `acta_nacimiento` → path patient as beneficiario; do **not** promote parent CI from acta text.

## Edge-case matrix

| Case | Symptom | Fix |
| --- | --- | --- |
| Path vs CI | FACT stem is patient; plastic CI is insured | Path → beneficiario; CI → titular |
| Menor | No personal cédula; forms say C.I. MENOR | Name-only person; acta = identity docs |
| Acta mislabel | Page titled cédula but registro civil body | `acta_nacimiento`; clear false `person_id` if needed |
| Collage mislabel | Cédula+carnet sheet as otro anexo | `documentos_identificacion`; attach invoice CI titular if OCR weak |
| Weak collage OCR | Only provider RIF extracted | Keep invoice titular with CI; do not invent person from RIF (`extract_personal_identity` returns None) |
| Two cards on a collage | Titular + patient cédulas on one page | Current titular CI among them → keep; otherwise `multiple_ci` review |
| Path CI ≠ plastic CI | Adult patient's CI in the FACT stem | Plastic-ID titular stays; path CI person → beneficiario |
| Nameless CI titular | CI row with no `full_name` | Do not link the path name as beneficiario (could be the same person) |
| Acta was typed as cédula | Parent CI became titular | Reclassify demotes that link to `unknown` when no other ID page supports it |
| Siniestro form | República / C.I. on claim planilla | Not `cedula_identidad` → comprobante / form rules |
| Glued FACT stem | `FACT 7394NAME SURNAME.pdf` | Strip invoice digits before name (`extract_titular_from_path`) |
| Workbook protect | Path name would overwrite enriched titular | Keep workbook person when CI/phone/DOB present |
| Contact hygiene | `0212-…` on factura tomador / clinic header | Do not write to `person.phone` |
| Patient phone | Informe `TELÉFONO` next to patient name | Candidate for `person.phone` |
| Domicilio on acta | Presentante address | Candidate for **titular** address, not child |
| Workbook phone | `TELEFONO` / `TELF.ASEGURADO` on a row with a beneficiario | Titular, not the beneficiario. Emergency column only → beneficiario |
| Letterhead phone | Clinic, insurer, RIF, or a number on 8+ invoices and 3+ titulares | Do not write. Gap `only_letterhead` |
| Scanner packet below 0.6 | Contact text in an unassigned lote | Do not write. Gap `unsegmented_scan` |
| Minor phone / address | Beneficiario hijo or under 18 with no own value | Leave empty. Gap `not_applicable_menor` |
| Wrong DOB on titular | Child DOB copied onto CI person | Correct from cédula F. nacimiento; workbook source was the beneficiary DOB column → `repair_workbook_birth_dates.py` |
| DOB disagreement | Two sources give different DOBs | Stored DOB stays; `dob_conflict` review |
| Spelling variant | Same child twice, one-letter OCR slip | `identity_resolver.py` (auto-merge only with equal DOB) |
| Claim form “FACTURA N°” | Siniestro form judged fiscal | `claim_form` → comprobante; never opens a scanner packet |
| Scanner packet, no invoice number | Pre-printed fiscal box unread | Key on control number → `invoice.control_number`; zero or several matches → skipped |
| Auth line without FACT | `authorization_line.invoice_id` null | `match_auth_lines.py` (clave, person, date window, amount, service) |

## Script / CLI map

Use project `.venv` and `PYTHONPATH=scripts`. Prefer unpooled DB URL from `env_load`.

| Script | Purpose | Typical invoke |
| --- | --- | --- |
| `document_types.py` | Classify / extract | imported; covered by unit tests |
| `person_upsert.py` | CI / name upsert + absorb | imported by loader / repairs |
| `upload_documents_to_blob.py` | Load pages → Neon + Blob | follow script `--help`; private Blob |
| `reclassify_identity_pages.py` | OCR-cache reclassify + role relink | `… --all --suspect-only --quiet [--apply]` or `--invoices a,b,c` (one is required) |
| `repair_corpus_person_roles.py` | Corpus CI titular + path beneficiario | `… --quiet` then `--apply`; `--role-cohort id_docs_no_ci`; opens `multiple_ci` reviews |
| `role_verify.py` | Per-invoice evidence cohorts + optional auto-safe repair | dry-run; `--write-cohort --apply`; `--repair --cohorts … [--apply]`; `--queue` |
| `role_cohorts.py` | Shared cohort predicates / actions | imported by verify + tests |
| `role_inventory.py` | Counts-only role gap report → `output/runs/` (includes verify cohorts when snapshot exists) | no flags |
| `role_linkage.py` | Beneficiario harvest / pair propagate / workbook relink | `beneficiario\|propagate\|workbook\|all [--apply] [--role-cohort mismatch_no_beneficiario]` |
| `cleanup_person_duplicates.py` | Junk + provisional merge | dry-run then `--apply` |
| `scripts/local_cases/*` | **Case-specific** one-off repairs (git-ignored, PHI) | pattern only; prefer generic phases for new people |
| `workbook_enrichment` | Register workbooks first | `python -m workbook_enrichment …` |
| `backfill_titulares.py` | Path/OCR titular gap fill | after workbook load; only replaces `legacy_unknown` sources |
| `repair_workbook_birth_dates.py` | Undo DOBs from the wrong workbook column | dry-run then `--apply` |
| `repair_workbook_contact.py` | Titular phone and address from sábana / claves / relación | dry-run then `--apply` |
| `enrich_person_contact.py` | OCR birth date, phone, address, plus `contact_gap` | dry-run then `--apply` |
| `identity_resolver.py` | Fuzzy duplicates → merge or `duplicate_candidate` | dry-run then `--apply` |
| `fiscal_extract.py` | Control no., date, totals, clave, fiscal titular/patient | `--apply --link-roles`; `--missing-titular` / `--roles-only` for role backfill |
| `match_auth_lines.py` | Score auth lines against invoices | dry-run then `--apply` (`--relink` to rescore linked lines) |
| `ocr_invoice_pages.py` | OCR cache; `--scope scan` for scanner lots | `--scope scan --folder "SCANER SEGURO MIRANDA" [--workers N]` (resumable) |
| `segment_scan_packets.py` | Group scanner pages into packets | `--folder …` then `--reviews` to open `segment_review` |
| `upload_documents_to_blob.py --scan-packets [CSV]` | Load segmented packets | `--min-confidence 0.6`; `--shard i/n` for parallel runs (32–64, one shell, `wait`) |

## Phase order and provenance

Run order for a corpus refresh: reclassify → DOB repair → resolver → fiscal extract → auth matcher → scanner OCR → segment → scanner load → auth matcher again → **`role_verify.py` → repair by cohort (`role_verify --repair` / `role_linkage --role-cohort` / `fiscal --missing-titular` / `repair_corpus_person_roles --role-cohort`) → `role_verify.py --write-cohort --apply` again** → `/revision`. Each step does a dry-run then `--apply`, and each writes an `etl_run` row plus a counts-only report at `output/runs/{run_id}.md`.

### Role verify cohorts (one primary per invoice)

Priority: `multi_titular` → `blocked_review` → `no_titular` → `id_docs_no_ci` → `mismatch_no_beneficiario` → `nameless_titular` → `resolved_pair` → `unknown_links` → `weak_evidence` → `self_visit_ok`.

Migration: [sql/010_invoice_role_cohort.sql](../../../sql/010_invoice_role_cohort.sql) (`invoice.role_cohort`, `role_verify_snapshot`, `v_invoice_role_cohort`). Reader Facturas filter: `?role_gap=mismatch|no_ci|nameless|blocked|multi`.

Provenance pattern for new code:

```python
import provenance

provenance.start_run(url, "my_script", vars(args), apply=args.apply)
with provenance.source("ocr", f"{relative}#{page}"):
    provenance.record(cur, entity="person", entity_id=pid, field="phone",
                      old=old_phone, new=new_phone, rule_id="informe_phone", confidence=0.8)
    provenance.open_review(cur, kind="dob_conflict", dedupe_key=f"dob_conflict:{pid}",
                           person_id=pid, evidence={...})
provenance.finish_run(url, dict(stats))
```

## Scanner-lot discovery

- Inventory rows with `rule_id = scan_outside_invoice` are scanner output with no FACT folder (most are Seguros Miranda; jpg one page per file, some pdf).
- Capture order per packet: fiscal sheet → claim form (siniestro / carta aval) → informe → other attachments. Files sort naturally (`IMG_9` before `IMG_10`).
- Packet key: printed invoice number, else the normalized control number (`SS-NNNNNN`).
- Confidence: key, both numbers, a claim form or carta aval as page 2, names that match across pages, and a plausible size (2–30 pages) all raise it; two claim forms in one packet lower it. Packets under 0.6 become `segment_review`.

Unit tests:

```bash
PYTHONPATH=scripts .venv/bin/python -m unittest \
  test_invoice_rules.DocumentTypeTests test_role_resolution
```

Reclassify (dry-run then apply):

```bash
PYTHONPATH=scripts .venv/bin/python scripts/reclassify_identity_pages.py \
  --invoices 1234,5678
PYTHONPATH=scripts .venv/bin/python scripts/reclassify_identity_pages.py \
  --invoices 1234,5678 --apply
```

Apply enums if missing:

```bash
# run sql/004 then sql/005 against DATABASE_URL_UNPOOLED
```

## Neon query templates

Replace placeholders. Do not paste real PHI into the skill or commit messages.

**Beneficiarios of a titular**

```sql
SELECT b.full_name, b.identity_number, count(DISTINCT i.id) AS invoices,
       max(bip.parentesco) AS parentesco
FROM avila.invoice_person tip
JOIN avila.invoice i ON i.id = tip.invoice_id
JOIN avila.invoice_person bip
  ON bip.invoice_id = tip.invoice_id
 AND bip.role = 'beneficiario'
 AND bip.person_id <> tip.person_id
JOIN avila.person b ON b.id = bip.person_id
WHERE tip.person_id = $titular_id::uuid AND tip.role = 'titular'
GROUP BY b.id, b.full_name, b.identity_number
ORDER BY 1;
```

**Titulares of a beneficiario**

```sql
SELECT t.full_name, t.identity_number, count(DISTINCT i.id) AS invoices,
       max(bip.parentesco) AS parentesco
FROM avila.invoice_person bip
JOIN avila.invoice i ON i.id = bip.invoice_id
JOIN avila.invoice_person tip
  ON tip.invoice_id = bip.invoice_id
 AND tip.role = 'titular'
 AND tip.person_id <> bip.person_id
JOIN avila.person t ON t.id = tip.person_id
WHERE bip.person_id = $beneficiario_id::uuid AND bip.role = 'beneficiario'
GROUP BY t.id, t.full_name, t.identity_number
ORDER BY 1;
```

**Role matrix for FACT list**

```sql
SELECT i.invoice_number, ip.role::text, p.full_name, p.identity_number,
       ip.parentesco, ip.source
FROM avila.invoice_person ip
JOIN avila.invoice i ON i.id = ip.invoice_id
JOIN avila.person p ON p.id = ip.person_id
WHERE i.invoice_number = ANY($facts)
ORDER BY i.invoice_number,
  CASE ip.role WHEN 'titular' THEN 0 WHEN 'beneficiario' THEN 1 ELSE 2 END;
```

**Suspect mislabeled identity pages**

```sql
SELECT i.invoice_number, d.page_index, d.document_type::text, d.evidence
FROM avila.document d
JOIN avila.invoice i ON i.id = d.invoice_id
WHERE i.invoice_number = ANY($facts)
  AND (
    (d.document_type = 'cedula_identidad' AND d.evidence ILIKE '%acta%')
    OR (d.document_type = 'otro_anexo' AND d.evidence ILIKE '%identific%')
    OR d.evidence = 'documentos_identificacion'
  )
ORDER BY 1, 2;
```

## Reader checks

- Documento detail: Spanish type label; **Ver perfil** / titular CTA; Personas del expediente list.
- Persona (titular): **Beneficiarios** section when others are `beneficiario` on their invoices.
- Persona (beneficiario): **Titular del expediente** banner + **Titulares** section (not notes-only).
- Persona: **Historial** lists field changes (source, rule, date, confidence).
- `/revision`: open items by kind; Aceptar merges duplicates, promotes the CI titular, or links the auth line; other kinds are acknowledged only.

## Related helpers (signatures)

- `try_promote_ci_titular(cur, invoice_id, person_id, *, path_name=None, path_ci=None) -> "promoted" | "workbook_titular" | "ci_conflict"` — the only entry point for CI → titular.
- `titular_promotion_blocker(cur, invoice_id, person_id)` — the guard on its own (dry-runs).
- `identity_page_ci(text, prefer=None) -> (ci, "ok" | "none" | "multiple")`.
- `promote_ci_person_as_titular(cur, invoice_id, person_id)` — unguarded primitive; demotes other titulares to beneficiario.
- `_link_path_name_as_beneficiario(cur, invoice_id, name, titular_id, path_ci=None)` — no-op if same CI, name subset, or nameless titular; upserts by CI when the path carries one.
- `upsert_by_ci` / `upsert_by_name` / `absorb_provisional` — [scripts/person_upsert.py](../../../scripts/person_upsert.py).
- `merge_person(cur, survivor_id, alias_id, *, reason)` — moves roles, documents, auth lines and review items to the survivor; fills empty fields; refuses two different CIs.
