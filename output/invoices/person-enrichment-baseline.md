# Person enrichment baseline

Snapshot before workbook load (Neon + `Avila-backup` inventory).

## Neon person coverage

| Metric | Value |
| --- | --- |
| Persons | 1,045 |
| With cédula (`identity_number`) | 113 (10.8%) |
| With `full_name` | 962 (92.1%) |
| Provisional keys | 932 |
| Orphan provisional (no invoice link) | 9 |

### Invoice–person roles

| Role | Count |
| --- | --- |
| titular | 974 |
| unknown | 78 |
| beneficiario | 0 |

## Workbook inventory

Command: `PYTHONPATH=scripts .venv/bin/python -m workbook_enrichment inventory`

| Family | Workbooks |
| --- | --- |
| sabana | 182 |
| cintillo | 87 |
| relacion | 43 |
| claves | 39 |
| amp | 32 |
| unknown | 11 |
| estado_cuenta | 1 |
| **Total scanned** | **395** (baremo/template paths skipped) |

Sheets with recognizable person headers: **299**. Full CSV: `output/invoices/workbook-inventory.csv`.

## Column map → canonical fields

| Canonical | Example source headers |
| --- | --- |
| `titular_name` | TITULAR, NOMBRE TITULAR, NOMBRE DEL TITULAR |
| `titular_ci` | CI TITULAR, C.I. TITULAR, first CEDULA DE IDENTIDAD |
| `beneficiario_name` | BENEFICIARIO, NOMBRE DEL PACIENTE |
| `beneficiario_ci` | CI BENEFICIARIO, C.I. PACIENTE, second CEDULA DE IDENTIDAD |
| `birth_date` | FECHA DE NACIMIENTO (1st) |
| `parentesco` | PARENTESCO |
| `phone` | TELEFONO, TELF.ASEGURADO, emergency contact phone |
| `address` | DIRECCION |
| `clave_rms` | CLAVE RMS, CLAVE DE AUTORIZACIÓN, AUTORIZACION |
| `contratante` | CONTRATANTE, EMPRESA /O INSTITUCION |
| `diagnosis` | DIAGNOSTICO, SINTOMA / DIAGNOSTICO |
| `service_description` | DESCRPCION DE SERVICIOS, DESCRIPCION DE SERVICIOS MEDICOS |
| `provider_name` / `provider_rif` | PROVEEDOR, RAZON SOCIAL / RIF |
| `amount_*` | MONTO BS / USD / COBERTURA / AUTORIZADO |
| `invoice_number` | NRO DE FACTURA |
| `control_number` / dates | NRO DE CONTROL, FECHA DE FACTURA / SERVICIO / SOLICITUD |

## Gaps this enrichment closes

1. Almost no structured CI on persons (10.8%) despite hundreds of workbook rows with CI TITULAR / CI BENEFICIARIO.
2. `beneficiario` role unused.
3. No phone, address, DOB, CLAVE, diagnosis, or amounts in Neon.
4. Path/OCR titulares often lack CI and never merge with cédula-only rows.
