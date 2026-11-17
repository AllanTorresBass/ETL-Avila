# Person cleanup report

## Summary

Redundant and junk `avila.person` rows were removed; loaders now use name-scoped provisional keys and shared absorb logic so the bloat does not return.

| Metric | Pre-cleanup | After |
| --- | ---: | ---: |
| Persons | ~2,374 | **1,564** |
| Without CI (provisional) | ~1,264 | **406** |
| Junk folder-name persons | ~128+ | **0** |
| Duplicate provisional name groups | 120 | **0** |
| Duplicate cédulas | 0 | **0** |

Second apply pass deleted 73 punctuated batch labels (`Facturas Agosto 1,`, etc.) after tightening junk detection.

## Code changes

- `scripts/person_upsert.py` — shared upsert + absorb; provisional key `name:{folded}`
- `scripts/document_types.py` — months / `FACTURAS` / years as path noise
- `scripts/cleanup_person_duplicates.py` — maintenance job (`--dry-run` / `--apply`)
- `scripts/upload_documents_to_blob.py` — shared upsert; workbook titular precedence
- Workbook enrichment delegates to `person_upsert`
- Architecture §14 updated

## Re-run

```bash
PYTHONPATH=scripts .venv/bin/python scripts/cleanup_person_duplicates.py
PYTHONPATH=scripts .venv/bin/python scripts/cleanup_person_duplicates.py --apply
PYTHONPATH=scripts .venv/bin/python -m unittest test_invoice_rules.DocumentTypeTests test_person_upsert
```
