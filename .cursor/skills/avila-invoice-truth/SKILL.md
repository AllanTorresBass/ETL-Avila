---
name: avila-invoice-truth
description: >-
  Rebuilds Ávila titular and beneficiario links from each factura packet.
  Read the fiscal line and the identity cards, decide self, pair, or review,
  then apply only clear links through try_promote_ci_titular and provenance.
  Use when roles or cédulas are linked wrong, when the user asks for invoice
  truth, or when running invoice_truth.py, invoice_truth_decide.py, or
  invoice_truth_apply.py.
---

# Ávila invoice truth

The factura packet is the evidence. Do not start from the person already on `avila.invoice_person`. Record of the first full apply: [docs/invoice-truth.md](../../../docs/invoice-truth.md). Person graph rules that this pass does not replace: [avila-etl-persons](../avila-etl-persons/SKILL.md).

## How, when, where

Every apply calls `provenance.start_run` / `finish_run`. Each field change is `provenance.record` inside `provenance.source("ocr", backup_path#page)`.

| Question | Stored as |
| --- | --- |
| How | `rule_id`: `invoice_truth_titular`, `invoice_truth_beneficiario`, `invoice_truth_page_person` |
| When | `avila.etl_run` window and `field_provenance.created_at` |
| Where | `source_kind` `ocr` and `source_ref` `backup_path#page` |
| Why | `reason` (`fiscal_ocr`, `ocr_cedula`, `self_only`, `not_in_decision`) |

Hashes only. Stdout and `output/runs/*.md` are counts. Names and cédulas stay in the git-ignored JSONL files.

## Order

Run from the repo root. Stop after decide until the counts in `output/runs/invoice-truth-decisions.md` are what you expect. Check `avila.etl_run` for `invoice_truth_apply` before a second `--apply`, so a run that already committed is not applied twice.

```bash
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth.py
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_decide.py
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py --apply --invoices 100,101
```

| Step | Script | Neon |
| --- | --- | --- |
| 1 Read | `scripts/invoice_truth.py` | No write. Optional `--limit` and `--invoices`. |
| 2 Decide | `scripts/invoice_truth_decide.py` | No write. Pure function `decide_record`. |
| 3 Apply | `scripts/invoice_truth_apply.py` | Dry-run unless `--apply`. |

Prefer `DATABASE_URL_UNPOOLED`. Tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts .venv/bin/python -m unittest scripts/test_invoice_truth.py`.

## What the read keeps

One JSON object per loaded factura in `output/runs/invoice-truth.jsonl`.

- Fiscal titular name and cédula, fiscal patient name and cédula, from `fiscal_extract.extract`.
- Cards: `cedula_identidad`, `carnet`, `documentos_identificacion`, `pasaporte`. Name from `extract_name_from_cedula_ocr`, numbers from `extract_all_cedulas`, then `sanitize_person_name`.
- Acta parent cédulas: numbers seen only on `acta_nacimiento`. They are not cards.
- Folder name and folder cédula, as a hint. `extract_titular_from_path`.

## What the decision means

First match wins.

| Outcome | Meaning |
| --- | --- |
| `review` / `acta_only` | No card cédula, no fiscal titular cédula, and the only numbers are acta parents. |
| `review` / `no_titular_ci` | No card cédula and no fiscal titular cédula. |
| `review` / `fiscal_card_mismatch` | Both exist and share none. |
| `review` / `unassigned_cards` | Two or more card cédulas and the fiscal lines do not place each one. |
| `review` / `unnamed_card` | A cédula was read and neither the card nor the fiscal line has a usable name. |
| `self` | Titular cédula resolved, and the patient is missing or matches that cédula or that name. |
| `pair` | Titular cédula resolved and the patient is a different person. |

Titular cédula: the fiscal number when a card repeats it, otherwise the single card number when the fiscal line has no number. Titular name: the name on that card, otherwise the fiscal name. A folder name becomes the patient only when the fiscal patient line is empty, the titular is resolved, and the folder name is a different person (`beneficiario_source: path`). A folder cédula never overrides a card.

Same person means equal cédula digits or `_names_refer_to_same_person`. A self-visit is one person.

## What apply writes

`review` rows are not linked. `unassigned_cards` opens `multiple_ci` with dedupe key `multiple_ci:{invoice_id}:invoice_truth`. Other review reasons stay in the decision file.

For `self` and `pair`:

- A usable stored name that fails `_names_refer_to_same_person` opens `ci_conflict` and skips the factura. A stored name that fails the name gate is treated as empty and may be filled.
- Titular goes through `try_promote_ci_titular` only. Source `fiscal_ocr` or `ocr_cedula`. Anything other than `promoted` skips the factura. Do not pass the folder name into that call.
- On `pair`, the patient is `upsert_by_ci` when they have a cédula, otherwise `upsert_by_name`. Role `beneficiario`. Skip when that person is the titular.
- On `self`, do not create a second person from the folder. After a successful promote, a `self` factura keeps only the titular link. A `pair` keeps the titular and that beneficiario. The old role is recorded before the extra link is removed.
- The card page `document.person_id` is set to the person that page names. A collage that holds both cédulas stays with the titular. An acta page is not given a parent as titular.

Phone, address, and birth date stay out of this pass.

## After apply

- Do not run `role_verify.py --repair`, `role_linkage.py`, or `repair_corpus_person_roles.py` on a factura marked `self` or `pair`. Those repairs keep the stored person as the anchor.
- Cohort repair in the persons skill is for facturas left in `review`.
- Contact fill runs only after a factura is `self` or `pair`, onto the person the page names, and only into an empty field.
- Staff resolve `ci_conflict` and `multiple_ci` at `/revision`. After a staff note, rerun apply with `--invoices` for that factura number.

## Stop

Do not guess when the decision is `review`. Do not merge two different cédulas. Do not promote an acta parent number or a RIF. Do not overwrite a workbook titular who already has a cédula, phone, or birth date.
