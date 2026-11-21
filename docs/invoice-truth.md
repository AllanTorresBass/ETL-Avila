# Invoice truth: titular and beneficiario from the packet

The factura packet is the evidence for who the titular is and who the patient is. This pass reads each loaded factura, decides the link, and writes only the decisions that are clear. Names, cédulas, and factura paths stay in git-ignored files under `output/runs/`. This document has counts and the procedure.

Playbook: [`.cursor/skills/avila-invoice-truth`](../.cursor/skills/avila-invoice-truth/SKILL.md) · Persons: [`.cursor/skills/avila-etl-persons`](../.cursor/skills/avila-etl-persons/SKILL.md) · Schema: [avila-etl-architecture.md](./avila-etl-architecture.md)

## How, when, and where

Every write is one row in `avila.field_provenance`, tied to `avila.etl_run`.

| Question | Where it is stored |
| --- | --- |
| How | `rule_id` |
| When | `avila.etl_run.started_at` / `finished_at`, and `field_provenance.created_at` |
| Where | `source_kind` + `source_ref` (backup path and page, for example `FACT 100.pdf#2`) |
| Why | `reason` |

Values are stored as short hashes. The provenance table does not keep a second copy of the name or the cédula.

The apply run is `bd9c1fc7-bad6-4b16-b0cc-f0a742a51724`, script `invoice_truth_apply`, mode `apply`. It started 2026-11-21 03:19 UTC and finished 2026-11-21 04:26 UTC.

| Step | Script | Writes Neon? | Output |
| --- | --- | --- | --- |
| Read | `scripts/invoice_truth.py` | No | `output/runs/invoice-truth.jsonl`, counts in `invoice-truth.md` |
| Decide | `scripts/invoice_truth_decide.py` | No | `output/runs/invoice-truth-decisions.jsonl`, counts in `invoice-truth-decisions.md` |
| Apply | `scripts/invoice_truth_apply.py` | Only with `--apply` | `avila.person`, `avila.invoice_person`, `avila.document.person_id`, `avila.review_item` |

Role source on `avila.invoice_person` is `fiscal_ocr` when the fiscal line supplied the cédula, `ocr_cedula` when only the card did, and `path` when the beneficiario name came from the folder. The folder number never overrides the card.

Rule ids for this pass:

- `invoice_truth_titular` — the card or fiscal cédula becomes the titular.
- `invoice_truth_beneficiario` — the patient is a second person.
- `invoice_truth_page_person` — the identity page points at the person that page names.

Promotion still goes through `try_promote_ci_titular`. A workbook titular who already has a cédula, phone, or birth date is not replaced.

## What was read

6,223 loaded facturas, on the night of 20–21 Nov 2026.

| What the packet showed | Facturas |
| --- | ---: |
| A fiscal titular line | 2,090 |
| A fiscal patient line | 149 |
| One card cédula | 552 |
| Two or more card cédulas | 870 |
| No card cédula | 4,801 |

A card is a `cedula_identidad`, `carnet`, `documentos_identificacion`, or `pasaporte` page. Numbers that appear only on an acta are listed as parent numbers and are not cards. A RIF is not a person.

## What was decided

| Outcome | Facturas | Meaning |
| --- | ---: | --- |
| `self` | 1,619 | The patient is the titular. One person. |
| `pair` | 150 | The patient is a different person. |
| `review` / `no_titular_ci` | 3,073 | No cédula on a card and none on the fiscal titular line. |
| `review` / `unassigned_cards` | 829 | Two or more card cédulas, and the fiscal lines do not place each one. |
| `review` / `unnamed_card` | 367 | A cédula was read and no usable name was read with it. |
| `review` / `fiscal_card_mismatch` | 126 | The fiscal titular cédula and the card cédulas share none. |
| `review` / `acta_only` | 59 | The only numbers are parent numbers on an acta. |

## What was written

| Result | Facturas |
| --- | ---: |
| Self-visit linked | 1,495 |
| Pair linked | 138 |
| Skipped, name already belongs to someone else | 135 |
| Skipped, existing titular guard | 1 |

A `self` factura keeps the titular link. A `pair` keeps the titular and that beneficiario. Other people who had been linked to that factura were detached, with the old role recorded first.

136 facturas opened `ci_conflict` on `/revision` (the 135 name mismatches plus the one guard). The 829 unplaced-card facturas opened `multiple_ci`. The other review reasons stay in `invoice-truth-decisions.jsonl` and were not turned into review rows.

Phone, address, and birth date were not part of this run. Contact fill stays a later pass, and only onto the person the page names, into an empty field.

## Run it again

From the repo root, dry-run first:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth.py
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_decide.py
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py
```

Write only after the counts in `output/runs/invoice-truth-decisions.md` look right. Limit the first write to a few factura numbers:

```bash
PYTHONPATH=scripts .venv/bin/python scripts/invoice_truth_apply.py --apply --invoices 100,101
```

Do not run `role_verify.py --repair`, `role_linkage.py`, or `repair_corpus_person_roles.py` on a factura this pass marked `self` or `pair`. Those repairs start from the person already stored on the factura and can undo the packet link. Cohort repair is for facturas left in `review`.
