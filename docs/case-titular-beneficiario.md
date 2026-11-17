# Case pattern: titular CI vs path patient (beneficiario)

Anonymized write-up of the first titular/beneficiario repair. The real names, cédulas, Neon ids, and
FACT paths live only in the local dossier `output/persons/{NAME}/case-notes.md` (git-ignored, PHI).

Playbook: [`.cursor/skills/avila-etl-persons`](../.cursor/skills/avila-etl-persons/SKILL.md) ·
Schema: [avila-etl-architecture.md](./avila-etl-architecture.md)

---

## 1. Problem

Invoice packets were named after the **patient** (`FACT NNNN BeneficiarioB.pdf`), but the plastic
identity documents in those packets belonged to the **insured titular** (TitularT, adult cédula).

Before the fix, the loader made the path name the titular, labeled birth certificates as cédulas,
filed ID collage sheets as `otro_anexo`, and the reader could not move between titular and beneficiario.

**Outcome:** TitularT is titular on six FACTs; BeneficiarioB is beneficiario (`parentesco = hijo`);
pages carry correct types; both profiles link to each other; TitularT contact fields come from packet OCR.

## 2. Final graph

| Role | Person | Identity | Contact |
| --- | --- | --- | --- |
| Titular | TitularT | Plastic CI (cédula + employer carnet) | DOB from cédula, phone from patient-labeled informe, address from acta domicilio of the presentante |
| Beneficiario | BeneficiarioB (menor) | None — acta de nacimiento is the identity proof | DOB from acta/workbook only |

Roles live on `avila.invoice_person`, never on `avila.person`.

## 3. Packet traits worth recognizing

- Stems glued to the invoice number (`FACT 7394NAME SURNAME.pdf`) — `extract_titular_from_path` strips the digits.
- One packet named after the titular with the CI in the stem (`FACT NNNN TitularT 12345678.pdf`).
- GPS cover `DOCUMENTOS DE IDENTIFICACION` holding cédula + carnet side by side.
- Acta pages quote the parents' cédulas and print CNE / República — they must never promote a titular.
- Near-miss names (same first name, different surname) exist in other folders — exclude them in discovery.

## 4. Steps taken

1. **Discover** — backup paths + Neon rows by name and CI; near-misses excluded.
2. **Inventory** — local dossier with `load-paths.txt` and `page-manifest.csv` from the OCR cache.
3. **People** — merged duplicate provisionals (`NAMESURNAME` → `NAME SURNAME`); `upsert_by_ci` for TitularT; name-only person for BeneficiarioB.
4. **Load** — packets to Neon + private Blob; optional card crops as pages `900`/`901` typed `cedula_identidad` / `carnet`.
5. **Roles** — `promote_ci_person_as_titular` + `_link_path_name_as_beneficiario`.
6. **Types** — `reclassify_identity_pages.py --invoices … --apply`; enums from `sql/004`, `sql/005`.
7. **Enrich** — phone/address/DOB onto the person the field describes; an uncertain alternate phone kept in `notes`; a child DOB that had been copied onto the titular was corrected from the cédula.
8. **Verify** — role matrix, identity page types, reader navigation, unit tests.

## 5. Page typing results

| Real page content | Before | After |
| --- | --- | --- |
| GPS sheet with cédula + carnet | `otro_anexo` | `documentos_identificacion` |
| Registro civil / birth certificate | `cedula_identidad` | `acta_nacimiento` |
| Standalone cédula crop | ok | `cedula_identidad` |
| Standalone employer badge | missing enum | `carnet` |
| Siniestro / planilla printing “República…” | false `cedula_identidad` | `comprobante` |

## 6. Remaining gaps (generic)

- Workbook authorization rows without a FACT number cannot be auto-linked to an invoice.
- Relatives named only on an acta (e.g. the other parent) are not modeled unless requested.
- Legal full name from the acta may differ from the short path name; product decides which to store.
