# Person enrichment — load report

## Applied

- Migration: `sql/003_person_enrichment.sql`
- Families: sabana (182), claves (30), relacion (43), amp (32), estado_cuenta (1)
- Cintillos skipped for row extract (image-heavy sheets; path family only)

## Neon after load

| Metric | Before | After |
| --- | ---: | ---: |
| Persons | 1,045 | 2,328 |
| With CI | 113 (10.8%) | 1,107 (47.6%) |
| With phone | 0 | 29 |
| With birth_date | 0 | 706 |
| With address | 0 | 207 |
| Authorization lines | 0 | 5,292 |
| Lines with person_id | — | 5,261 |
| Lines with invoice_id | — | 2 |

### Roles

| Role | Count |
| --- | ---: |
| titular | 1,209 |
| unknown | 85 |
| beneficiario | 1 |

Beneficiario invoice links stay rare because most register FACT numbers (e.g. `3704`, `4277`) are **not yet present** as `avila.invoice` rows (reader load focused on higher FACT packets). Persons and `authorization_line` rows are still searchable on `/personas` via CI / name / phone / CLAVE.

Invoice matching now strips zero-padding (`004277` → `4277`); re-run `--family relacion` after more invoices are loaded to attach roles.

## Commands

```bash
uv venv .venv && uv pip install -r scripts/requirements-enrichment.txt
psql "$DATABASE_URL_UNPOOLED" -f sql/003_person_enrichment.sql
PYTHONPATH=scripts .venv/bin/python -m workbook_enrichment inventory
PYTHONPATH=scripts .venv/bin/python -m workbook_enrichment run --apply --family sabana
PYTHONPATH=scripts .venv/bin/python -m unittest test_workbook_enrichment
```

## Reader

`/personas` and `/personas/[id]` show phone, DOB, address, and authorization lines. Factura detail shows parentesco and auth lines when `invoice_id` is set.
