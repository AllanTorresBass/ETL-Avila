# Invoice universe load report

Counts only. No patient names or cédulas.

## Pilot (20 source files)

| Measure | Value |
| --- | ---: |
| Source files | 20 |
| Documents | 160 |
| Uploaded to Blob | 160 |
| Failed | 0 |
| Persons resolved | 1 |
| Invoices touched | 13 |

### Document types in the pilot

| Type | Pages |
| --- | ---: |
| ilegible | 41 |
| informe_medico | 28 |
| factura_fiscal | 25 |
| carta_aval | 18 |
| orden_servicio | 17 |
| cedula_identidad | 11 |
| laboratorio | 9 |
| otro_anexo | 9 |
| imagenologia | 2 |

## Full load

Started after the pilot with `scripts/upload_documents_to_blob.py` against the full invoice-universe inventory (**17,248** source files). Progress is appended to `output/invoices/full-load.log`. The job is resumable: already uploaded pages are skipped.

Re-run anytime:

```bash
export PATH="/opt/homebrew/bin:$PATH"
python3 -u scripts/upload_documents_to_blob.py
```

Blob store linked in `.env` is a **public** store, so uploads use `access: 'public'`. The reader still proxies previews via `/api/blob/[id]`.
