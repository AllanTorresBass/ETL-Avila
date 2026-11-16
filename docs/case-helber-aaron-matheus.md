# Case study: Helber (titular) + Aaron Matheus (beneficiario)

**Date:** 2026-11-16  
**Account:** Seguros Miranda / contratante BDV  
**Purpose:** Document the full approach used to resolve one family expediente from `Avila-backup` into Neon + private Blob + the ETL reader — so the same pattern can be reused for other titular/beneficiario packets.

Related: [avila-etl-architecture.md](./avila-etl-architecture.md) · local dossier `output/persons/AARON MATHEUS/` (PHI; do not commit scans).

**Reuse:** apply the same approach to other people via Cursor skill [`avila-etl-persons`](../.cursor/skills/avila-etl-persons/SKILL.md) (phases discover → inventory → people → load → roles → types → enrich → verify).

---

## 1. Problem we solved

Invoice packets were named after the **patient** (`FACT … AARON MATHEUS.pdf`), but the plastic identity documents in those packets belong to the **insured titular** (Helber Jose Matheus Andara, CI `13996036`).

Without a clear rule set, the loader treated the path name as titular, mislabeled birth certificates as cédulas, dumped ID collage sheets as “otro anexo”, and left the reader unable to navigate titular ↔ beneficiario.

**Outcome:** Helber is titular on six FACTs; Aaron is beneficiario (hijo); pages are named correctly; both profiles link to each other; Helber’s contact fields are filled from packet OCR.

---

## 2. People (final Neon state)

| Role | Full name | Neon `person.id` | CI | DOB | Phone | Address |
| --- | --- | --- | --- | --- | --- | --- |
| **Titular** | HELBER JOSE MATHEUS ANDARA | `ba69bb1a-bdb6-432b-9f56-77997f975166` | `13996036` | 1979-07-15 | `04147341569` | Sector el Filo, Av. 4, Casa s/n, Parroquia San Rafael de Carvajal, Municipio Carvajal, Edo. Trujillo |
| **Beneficiario** | AARON MATHEUS (acta: Aaron Gabriel Matheus Blanco) | `e93257b2-63aa-4d23-a958-912dbc97b477` | — (menor) | 2015-04-22 | — | — |

Reader:

- Helber: `/personas/ba69bb1a-bdb6-432b-9f56-77997f975166`
- Aaron: `/personas/e93257b2-63aa-4d23-a958-912dbc97b477`

**Modeling rule (kept on `invoice_person`, not on `person.role`):**

- One **titular** per invoice (the insured / CI on plastic ID).
- Zero or more **beneficiarios** (path patient, acta child, etc.).
- Optional `parentesco` (here: `hijo`).

---

## 3. Packets in scope

| FACT | Backup path (under `Avila-backup/`) | Pages | Notes |
| ---: | --- | ---: | --- |
| 7316 | `FACTURAS/CASOS SEGURO MIRANDA FACTURAS/FACT  7316 AARON MATHEUS.pdf` | 6 | |
| 7394 | `FACTURAS/CASOS SEGURO MIRANDA FACTURAS/FACT 7394AARON MATHEUS.pdf` | 9 | Stem glued `7394AARON` — path parser must strip invoice digits |
| 7759 | `FACTURAS/FACTURAS S, MIRANDA JULIO 2/FACT 7759 AARON MATHEUS.pdf` | 12 | |
| 7798 | `FACTURAS/FACTURAS S, MIRANDA JULIO 2/FACT 7798 AARON MATHEUS.pdf` | 6 | Canonical mislabel example (p5 collage / p6 acta) |
| 7799 | `FACTURAS/FACTURAS S, MIRANDA JULIO 2/FACT 7799 AARON MATHEUS.pdf` | 9 | |
| 8322 | `FACTURAS/FACTURA S. MIRANDA AGOSTO LOTE 2/FACT 8322 HELBER MATHEUS 13996036.pdf` | 6 | Helber-named; same CI; patient form phone |

Excluded near-misses: `CASOS VNET/AARON CONTRERAS.pdf` and other Matheus surnames.

---

## 4. Approach (step by step)

### 4.1 Discover and inventory

1. Search backup paths for `AARON MATHEUS` / Helber CI `13996036`.
2. Build a local dossier under `output/persons/AARON MATHEUS/` (copies + manifests only; originals stay in `Avila-backup`).
3. Run / reuse OCR cache (`output/invoices/ocr/`) and produce `page-manifest.csv`.

### 4.2 Resolve people in Neon

1. Merge duplicate provisional Aaron rows (`AARONMATHEUS` → `AARON MATHEUS`).
2. Upsert Helber by CI `13996036` from cédula OCR / crops.
3. Keep Aaron as name-only provisional (`identity_type = unknown`) — **no personal cédula exists** in the packets (menor).

### 4.3 Load packets to Neon + private Blob

```bash
# paths listed in output/persons/AARON MATHEUS/load-paths.txt
PYTHONPATH=scripts .venv/bin/python scripts/upload_documents_to_blob.py …
```

- One page → one `avila.document` + one Blob object (`BLOB_ACCESS=private`).
- Also upload **split crops**: Helber cédula + BDV carnet as pages `900` / `901` on FACT 7394.

### 4.4 Role resolution (core business rule)

Implemented in `scripts/upload_documents_to_blob.py`:

| Signal | Role |
| --- | --- |
| Plastic ID / carnet / ID-collage CI | **Titular** (`promote_ci_person_as_titular`) |
| FACT path patient name when different from CI person | **Beneficiario** (`_link_path_name_as_beneficiario`) |
| Workbook titular with CI/contact | Protected from weak path overwrites |

Case repair helper: `scripts/repair_aaron_matheus_case.py` (Helber titular + Aaron beneficiario / `hijo` on all six FACTs).

### 4.5 Name documents correctly

| Real page content | Wrong label (before) | Correct type |
| --- | --- | --- |
| GPS sheet with cédula + BDV carnet side by side | `otro_anexo` | `documentos_identificacion` |
| Registro civil / birth certificate | `cedula_identidad` | `acta_nacimiento` |
| Standalone plastic cédula crop | (ok) | `cedula_identidad` |
| Standalone BDV badge crop | (missing enum) | `carnet` |
| Siniestro / planilla printing “República…” | false `cedula_identidad` | `comprobante` / not cédula |

Migrations:

- `sql/004_carnet_document_type.sql`
- `sql/005_identity_document_types.sql`

Classifier: `scripts/document_types.py`  
Reclassify from OCR cache: `scripts/reclassify_identity_pages.py --apply`

**FACT 7798 check:**

- p5 → Documentos de identificación → linked to Helber  
- p6 → Acta de nacimiento → linked to Aaron  

### 4.6 Enrich Helber contact from packets

| Field | Source | Confidence |
| --- | --- | --- |
| Phone `04147341569` | FACT 8322 informe (`TELÉFONO` on patient Helber) | Strong |
| Alt. `0424-4721721` | FACT 7316 ID collage (`contacto …`) | Likely; kept in `notes` |
| Address | Acta domicilio del presentante (Helber) | Strong |
| DOB `1979-07-15` | Cédula crop (fixed wrong Aaron DOB that had been copied onto Helber) | Strong |

Aaron: **no phone/address** in packets; identity proof is the **acta**, not a national ID.

### 4.7 Reader navigation

| Screen | Behavior |
| --- | --- |
| Documento detail | CTA **Ver perfil**; invoice **Personas del expediente** (titular / beneficiario links) |
| Persona (titular) | **Beneficiarios** section (Aaron × 6 facturas, parentesco hijo) |
| Persona (beneficiario) | Banner **Titular del expediente** + **Ver titular** + **Titulares** section + Titular field in identidad |

PRs that landed the approach: [#2](https://github.com/AllanTorresBass/ETL-Avila/pull/2) (CI titular + carnet), [#3](https://github.com/AllanTorresBass/ETL-Avila/pull/3) (identity types + nav).

---

## 5. What each person “owns” after load

### Helber (titular)

- Roles: titular on FACTs 7316, 7394, 7759, 7798, 7799, 8322  
- Identity docs: cédula crop, carnet crop, ~6 `documentos_identificacion` collage pages  
- Demographics: CI, DOB, phone, address, BDV employer notes  
- Beneficiarios: **1** (Aaron)

### Aaron (beneficiario)

- Roles: beneficiario on the same six FACTs  
- Identity docs: **5 × `acta_nacimiento`** (no cédula/carnet of his own)  
- Demographics: DOB only; full legal name on acta text  
- Clinical/auth: **24** `authorization_line` rows from Miranda sábana/claves (still mostly `invoice_id` null)  
- Titulares: **1** (Helber)

Expediente pages (facturas, informes, comprobantes) hang off the **invoice**, not only off `document.person_id`, so both profiles can browse the shared packet via invoice joins.

---

## 6. Decision rules (reuse checklist)

Use this for the next similar case:

1. **Path name ≠ plastic CI name** → path person is likely beneficiario/paciente; CI person is titular.  
2. **Minor patient** → expect acta / “C.I. MENOR”, not a child cédula.  
3. **`DOCUMENTOS DE IDENTIFICACION` cover** → type `documentos_identificacion`, not `otro_anexo`.  
4. **Registro civil / Acta N° / CNE comisión** → `acta_nacimiento`, even if the text quotes a parent’s cédula.  
5. **Never promote acta CI mentions to titular** (those are parents/registrar).  
6. **Crops** of cards stay as `cedula_identidad` / `carnet` with explicit `person_id`.  
7. **Reader must expose titular ↔ beneficiario** as first-class links, not only notes text.  
8. **Contact fields** come from patient-labeled forms / domicile lines, never from insurer letterhead phones (`0212-…` BDV) or clinic letterheads.

---

## 7. Scripts and artifacts

| Artifact | Role |
| --- | --- |
| `scripts/document_types.py` | Classification + path/OCR titular extract |
| `scripts/upload_documents_to_blob.py` | Load + role promotion |
| `scripts/repair_aaron_matheus_case.py` | Case-specific merge / role / Helber attach |
| `scripts/repair_aaron_identity_docs.py` | Crop upload / type repair |
| `scripts/reclassify_identity_pages.py` | OCR-cache reclassify for FACT lists |
| `scripts/test_invoice_rules.py` / `test_role_resolution.py` | Unit coverage |
| `sql/004_carnet_document_type.sql` | Enum `carnet` |
| `sql/005_identity_document_types.sql` | Enums `documentos_identificacion`, `acta_nacimiento` |
| `output/persons/AARON MATHEUS/*` | Local dossier (PHI scans — keep out of git) |

---

## 8. Remaining gaps

- Aaron has **no personal CI**; consider storing full acta name `Aaron Gabriel Matheus Blanco` on `person.full_name` if product wants legal name.  
- **24 auth lines** still lack `invoice_id` (workbook rows do not carry FACT numbers).  
- Alternate collage phone `0424-4721721` is only in Helber `notes`, not in `phone`.  
- Broader corpus may still have pre-fix false cédulas — run `reclassify_identity_pages.py` with a wider `--invoices` list when ready.  
- Mother on acta (Yenny Coromoto Blanco Perez) is **not** modeled as a person row yet.

---

## 9. Verification commands

```bash
# Classifier / role unit tests
PYTHONPATH=scripts .venv/bin/python -m unittest \
  test_invoice_rules.DocumentTypeTests test_role_resolution

# Reclassify Aaron packets (dry-run then apply)
PYTHONPATH=scripts .venv/bin/python scripts/reclassify_identity_pages.py
PYTHONPATH=scripts .venv/bin/python scripts/reclassify_identity_pages.py --apply

# Spot-check roles
# Helber titular + Aaron beneficiario on 7316/7394/7759/7798/7799/8322
```

Manual UI: search Personas → Helber → Beneficiarios → Aaron → **Ver titular** back to Helber; open FACT 7798 p5/p6 and confirm Spanish type labels + profile CTAs.
