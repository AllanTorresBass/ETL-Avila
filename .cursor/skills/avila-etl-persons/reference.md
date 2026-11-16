# Ávila ETL persons — reference

Dense lookup for [SKILL.md](SKILL.md). No patient PHI in this file.

## Document-type precedence

`classify_document` in [scripts/document_types.py](../../../scripts/document_types.py) must resolve in this order after fiscal / unreadable:

| Order | Type code | Spanish label | Win when |
| ---: | --- | --- | --- |
| 1 | `acta_nacimiento` | Acta de nacimiento | Registro civil, acta N°, comisión de registro, presentación del nacido |
| 2 | `documentos_identificacion` | Documentos de identificación | GPS cover `DOCUMENTOS DE IDENTIFICACION` (cédula + carnet collage) |
| 3 | `carnet` | Carnet | BDV / employer badge cues without dominating plastic cédula title |
| 4 | `cedula_identidad` | Cédula de identidad | `CEDULA DE IDENTIDAD` + card fields; not forms or actas |
| 5 | `pasaporte` | Pasaporte | Passport card (not fiscal “C.I., R.I.F. o PASAPORTE” alone) |
| 6 | `comprobante` | Comprobante | Incl. declaración de siniestro / planilla |
| 7 | clinical / path | egreso, ingreso, informe, lab, … | Path or OCR clinical tokens |
| 8 | `otro_anexo` | Otro anexo | Residual |

Migrations: [sql/004_carnet_document_type.sql](../../../sql/004_carnet_document_type.sql), [sql/005_identity_document_types.sql](../../../sql/005_identity_document_types.sql).

Loader identity linking ([scripts/upload_documents_to_blob.py](../../../scripts/upload_documents_to_blob.py)):

- `cedula_identidad` / `pasaporte` / `carnet` / `documentos_identificacion` → upsert CI person, promote titular, path name → beneficiario when different.
- `acta_nacimiento` → path patient as beneficiario; do **not** promote parent CI from acta text.

## Edge-case matrix

| Case | Symptom | Fix |
| --- | --- | --- |
| Path vs CI | FACT stem is patient; plastic CI is insured | Path → beneficiario; CI → titular |
| Menor | No personal cédula; forms say C.I. MENOR | Name-only person; acta = identity docs |
| Acta mislabel | Page titled cédula but registro civil body | `acta_nacimiento`; clear false `person_id` if needed |
| Collage mislabel | Cédula+carnet sheet as otro anexo | `documentos_identificacion`; attach invoice CI titular if OCR weak |
| Weak collage OCR | Only provider RIF extracted | Keep invoice titular with CI; do not invent person from RIF |
| Siniestro form | República / C.I. on claim planilla | Not `cedula_identidad` → comprobante / form rules |
| Glued FACT stem | `FACT 7394NAME SURNAME.pdf` | Strip invoice digits before name (`extract_titular_from_path`) |
| Workbook protect | Path name would overwrite enriched titular | Keep workbook person when CI/phone/DOB present |
| Contact hygiene | `0212-…` on factura tomador / clinic header | Do not write to `person.phone` |
| Patient phone | Informe `TELÉFONO` next to patient name | Candidate for `person.phone` |
| Domicilio on acta | Presentante address | Candidate for **titular** address, not child |
| Wrong DOB on titular | Child DOB copied onto CI person | Correct from cédula F. nacimiento |

## Script / CLI map

Use project `.venv` and `PYTHONPATH=scripts`. Prefer unpooled DB URL from `env_load`.

| Script | Purpose | Typical invoke |
| --- | --- | --- |
| `document_types.py` | Classify / extract | imported; covered by unit tests |
| `person_upsert.py` | CI / name upsert + absorb | imported by loader / repairs |
| `upload_documents_to_blob.py` | Load pages → Neon + Blob | follow script `--help`; private Blob |
| `reclassify_identity_pages.py` | OCR-cache reclassify + role relink | `… --all --suspect-only --quiet --apply` or `--invoices a,b,c` |
| `repair_corpus_person_roles.py` | Corpus CI titular + path beneficiario | `… --quiet --apply` after reclassify |
| `cleanup_person_duplicates.py` | Junk + provisional merge | dry-run then `--apply` |
| `repair_aaron_matheus_case.py` | **Case-specific** example repair | pattern only; prefer generic phases for new people |
| `repair_aaron_identity_docs.py` | **Case-specific** crop/type repair | pattern only |
| `workbook_enrichment` | Register workbooks first | `python -m workbook_enrichment …` |
| `backfill_titulares.py` | Path/OCR titular gap fill | after workbook load |

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

## Related helpers (signatures)

- `promote_ci_person_as_titular(cur, invoice_id, person_id)` — demotes other titulares on that invoice to beneficiario, links CI person as titular.
- `_link_path_name_as_beneficiario(cur, invoice_id, name, titular_id)` — upserts path name; no-op if same as titular.
- `upsert_by_ci` / `upsert_by_name` / `absorb_provisional` — [scripts/person_upsert.py](../../../scripts/person_upsert.py).
