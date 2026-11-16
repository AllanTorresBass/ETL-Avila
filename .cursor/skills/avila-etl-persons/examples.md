# Ávila ETL persons — examples

## How to invoke

User asks to fix a person, FACT packet, mislabeled cédula/acta/collage, or titular/beneficiario link.

1. Read [SKILL.md](SKILL.md) and run phases 1–8.
2. Use [reference.md](reference.md) for classify precedence, CLI, and SQL templates.
3. For a full PHI walkthrough already completed in-repo, see [docs/case-helber-aaron-matheus.md](../../../docs/case-helber-aaron-matheus.md) — do not copy cédulas or Neon UUIDs into the skill or commit messages.

## Anonymized walkthrough (path patient ≠ plastic CI)

**Setup**

- Backup packets named `FACT NNNN BeneficiarioB.pdf` (and maybe one `FACT MMMM TitularT {ci}.pdf`).
- Inside packets: GPS **documentos de identificación** collage with TitularT’s cédula + employer carnet; separate **acta de nacimiento** for BeneficiarioB (menor); informes naming BeneficiarioB as patient; one informe for TitularT with a `TELÉFONO` field.

**Expected graph**

| Role | Person | Identity |
| --- | --- | --- |
| Titular | TitularT | Plastic CI from collage/cédula |
| Beneficiario | BeneficiarioB | No personal CI; acta + path name; `parentesco` if known |

**Phase highlights**

1. **Discover** — Match FACT stems to BeneficiarioB; exclude other people who share only a first name.
2. **Inventory** — `output/persons/BeneficiarioB/load-paths.txt` + page manifest; mark collage vs acta vs informe.
3. **People** — `upsert_by_ci` TitularT; `upsert_by_name` BeneficiarioB; merge duplicate provisionals.
4. **Load** — Upload missing packets to private Blob if Neon lacks pages.
5. **Roles** — Promote TitularT; link BeneficiarioB as beneficiario on every shared FACT.
6. **Types** — Collage → `documentos_identificacion`; birth registry → `acta_nacimiento`; never leave acta as `cedula_identidad` or collage as `otro_anexo`.
7. **Enrich** — TitularT phone from patient-labeled informe; address from acta domicilio of the presentante when that is TitularT; BeneficiarioB DOB from acta/workbook only.
8. **Verify** — Role matrix shows one titular + beneficiario per FACT; reader beneficiario page has **Ver titular**; unit tests still pass.

**Done when**

- Document pages show correct Spanish labels.
- Titular profile lists BeneficiarioB under Beneficiarios.
- Beneficiario profile links to TitularT without relying on free-text notes alone.
- PHI scans remain local under `output/persons/…` and are not committed.

## Anti-patterns

- Treating FACT path name as titular when a different CI appears on plastic ID pages.
- Promoting parent/registrar CI from acta OCR to `invoice_person.titular`.
- Writing BDV/clinic letterhead phones onto `avila.person.phone`.
- Committing cédula/carnet PNG crops or full FACT PDFs from the dossier.
- Stopping after notes text (“titular is …”) instead of `invoice_person` links and reader sections.
