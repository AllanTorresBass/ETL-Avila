# Corpus person / identity repair report

**Date:** 2026-11-16  
**Playbook:** `.cursor/skills/avila-etl-persons/`

## Scope

Applied the Helber/Aaron approach across loaded Neon documents (not a full re-upload of `Avila-backup`).

| Metric | Before (approx.) | After |
| --- | ---: | ---: |
| `cedula_identidad` pages | 1,574 | 216 |
| `documentos_identificacion` | 6 | 870 |
| `acta_nacimiento` | 5 | 60 |
| `beneficiario` links | 7 | 37 |
| `titular` links | 630 | 688 |
| Invoices with CI titular + beneficiario | — | 32 |
| Titular still no CI but ID docs present | 256 | 124 |

## Steps run

1. **Reclassify** — `reclassify_identity_pages.py --all --suspect-only --apply`  
   - Scanned 5,304 suspect pages; **2,095** type changes; **131** person links during reclassify.  
   - Top moves: `otro_anexo`→`documentos_identificacion` (634); false `cedula_identidad`→informe/orden/otro/collage/acta/…
2. **Roles** — `repair_corpus_person_roles.py --apply`  
   - 926 invoices with identity-typed docs; **121** CI titular promotions; **21** path beneficiarios (after later cleanup).  
   - **805** skipped: no reliable CI on page OCR / linked person (weak collage OCR).
3. **Cleanup** — removed **6** false beneficiarios whose path name was the same person as the titular (e.g. short form of titular name).
4. **Guard** — `_link_path_name_as_beneficiario` now skips name-subset matches so path `Helber Matheus` does not become a second person under CI titular Helber Jose Matheus Andara.

## Remaining gaps

- **124** invoices still have a name-only titular while collage/cédula pages exist but OCR did not yield a clean CI — needs stronger CI extraction or manual crop review.
- **Contact enrichment** (phone/address) was **not** bulk-applied (patient-labeled OCR only; too risky corpus-wide without review).
- **Auth `invoice_id`** still null where workbooks lack FACT numbers.
- Full `--all` reclassify of non-suspect types (e.g. every informe) not required for this pass.

## Commands

```bash
PYTHONPATH=scripts .venv/bin/python scripts/reclassify_identity_pages.py \
  --all --suspect-only --quiet --apply
PYTHONPATH=scripts .venv/bin/python scripts/repair_corpus_person_roles.py \
  --quiet --apply
PYTHONPATH=scripts .venv/bin/python -m unittest \
  test_invoice_rules.DocumentTypeTests test_role_resolution
```
