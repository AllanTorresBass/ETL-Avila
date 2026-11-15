# Avila-backup data catalog

Inventory of `/Users/optec-123/Desktop/Allan-Projects/Avila/ETL/Avila-backup`, taken 13 November 2026 by walking every file in the folder.

This backup belongs to **G.P.S. Gestión Profesional de Salud Avila, C.A.** (GPS Avila), a medical provider in Valera, Trujillo. The files are the paperwork and registers used to request, authorize, deliver, and invoice medical services for insurers and corporate accounts.

The catalog describes **file types and how folders classify them**. It does not list patients, identity numbers, diagnoses, or phone numbers. Those values are inside the files.

## Snapshot

| Measure | Value |
| --- | ---: |
| Files (excluding `.DS_Store` and Office lock files) | 70,107 |
| Folders | 987 |
| Size | 116,990,461,729 bytes (109 GB) |
| Empty files | 1 (a leftover `.tmp`) |
| Dominant years in folder names | 2024 (24 folders), 2025 (237), 2026 (263) |

Almost all of the bytes are pictures of paper. Spreadsheets are the only consistently structured data, and they are a small fraction of the file count.

## 1. Physical data types

| Extension | Files | Size | What the bytes actually are |
| --- | ---: | ---: | --- |
| `.pdf` | 38,314 | 50.0 GB | Scanned pages, PowerPoint exports, and a smaller set of real forms (budgets, supply sheets) |
| `.jpg` | 30,919 | 28.4 GB | Camera or scanner photos of the same kinds of documents. Samples are about 200 DPI, letter-sized, often grayscale |
| `.pptx` | 359 | 24.9 GB | Binders of document photos, one image per slide. A typical file has 6–16 slides and tens of megabytes of embedded images |
| `.potx` | 67 | 3.9 GB | Same photo-binder pattern, saved as a PowerPoint template |
| `.rar` | 2 | 1.8 GB | Compressed copies of two October 2026 Seguros Miranda scanner lots |
| `.ppt` | 1 | 64 MB | One older PowerPoint invoice binder |
| `.png` | 17 | 33 MB | A few scanner pages saved as PNG, plus invoice images in `FACTURAS/IMPRIMIR` |
| `.xlsx` | 387 | 22 MB | Structured registers: sábanas, claves, relaciones, baremos, cintillos, invoice templates |
| `.xls` | 32 | 5.1 MB | Seguros Venezuela “AMP (servicio inmediato)” service-request workbooks (Excel 97–2003) |
| `.docx` | 2 | 130 KB | One ophthalmology note and one gynecology consult note |
| `.lnk` | 4 | 4 KB | Windows shortcuts. They point at disks, not at records |
| `.ini` | 1 | 46 B | `desktop.ini` left by Windows Explorer |
| `.tmp` | 1 | 0 B | Empty PowerPoint temp file |
| no extension | 1 | 64 KB | `FACTURAS/VERIFICACION IRAIMA CASTELLANO` |

### How to tell the PDFs apart

Three PDF populations sit under the same extension:

1. **Scanner pages.** Name pattern `Escáner_YYYYMMDD (n).pdf`. One page, no text layer, page size around 826 × 1169 pt. `pdftotext` returns a blank page. This is the bulk of `SCANER SEGURO MIRANDA` and the loose November/October scanner folders.
2. **PowerPoint exports.** `pdfinfo` reports Creator `Microsoft PowerPoint 2013` and a title of “Presentación de PowerPoint”. Several pages, letter size. Case files such as `APS 5909.pdf` are in this group. The text layer is empty because the content is pictures placed on slides.
3. **Generated forms.** Budgets and the hospital-supply format PDFs have real text (codes, quantities, amounts) plus a logo image.

JPG samples confirm the same source: invoice photos at 1699 × 2239 px, 200 DPI, and Cemento Andino camera photos at 2512 × 3168 px.

### PowerPoint files are document binders

`.pptx`, `.potx`, and `.ppt` are the clinic’s way of stapling several scanned pages into one file: carta aval, invoice, discharge summary, pre-employment exam. They are large because each slide embeds a photo. Many of those binders were also exported to PDF, so the same case often exists twice.

## 2. How the data is categorized

A file’s meaning comes from five labels, almost all of them written into the folder or file name. There is no database, index, or metadata sidecar.

| Axis | Where it is written | Examples |
| --- | --- | --- |
| Channel | Top-level folder | `SCANER SEGURO MIRANDA`, `FACTURAS`, `SEGUROS MIRANDA`, `PREVISORA` |
| Account | Folder title | Previsora, Latitud, Hispana, Altamira, Constitución, SENIAT, Cemento Andino |
| Period | Month, year, `LOTE`, `PARTE` | `OCTUBRE LOTE 4, 2026`, `PARTE 2` |
| Document role | File or folder prefix | `FACT`, `CARTA AVAL`, `EGRESO`, `SABANA`, `BAREMO`, `RELACION`, `CINTILLO`, `PRESUPUESTO` |
| Workflow state | Subfolder | `procesadas`, `facturas procesadas`, `listas`, `Digitalizaciones`, `detalles` |

### Path grammar

```text
SCANER SEGURO MIRANDA / SCANER SEG. MIRANDA OCTUBRE LOTE 4, 2026 / Procesadas / Escáner_20261011 (754).pdf
        channel              account + month + lot + year          state              one scanned page, 11 Oct 2026

FACTURAS / FACTURAS ALTAMIRA SEPTIEMBRE LOTE 2, 2025 / FACT 14029.pdf
  channel        account + month + lot + year                         issued invoice

SEGUROS MIRANDA / FORMATO SABANA JUNIO LOTE 1 GPS AVILA 4.6.24.xlsx
     channel              register type + month + lot + provider + date
```

Spelling is unstable. The same idea appears as `SCANER`, `ESCANER`, `SCANNER`, `SCAR`, and `SCAN`. Processed folders appear as `procesadas`, `Procesadas`, `FACTURAS PROCESADAS`, and `facturas procesadas`. Account names are misspelled in places (`ANDONO`, `CONTITUCION`, `PREVISA`, `LATITUC`, `PIRAMIRE`, `SENIA`).

### Workflow state of every file

State is only a folder name. A file sitting in a `procesadas` folder has been moved there by someone; the file itself has no status field.

| State inferred from the path | Files |
| --- | ---: |
| No processed / listas / digitalizaciones folder in the path | 46,430 |
| Inside a `procesadas` (or `facturas procesadas`) folder | 23,296 |
| Inside a `listas` folder | 301 |
| Inside a `Digitalizaciones` folder | 80 |

Inside `SCANER SEGURO MIRANDA` there are **125 scanner-batch folders**. **60** of them contain a processed subfolder and **65** do not. That parent folder also holds **96** single-invoice folders and **85** carta-aval case folders, plus 14 loose files.

### Document lifecycle the names describe

The names line up with one billing cycle:

1. **Request** — cintillo, solicitud, AMP servicio inmediato, clave workbook.
2. **Authorization** — carta aval, clave RMS, authorization name on the relación.
3. **Clinical packet** — scanner pages, ingreso, egreso, informe, verificación, exam photos.
4. **Invoice** — `FACT` plus a number, sometimes with the patient name and cédula in the file name.
5. **Batch register** — sábana or relación for that month and lot, the spreadsheet sent with the invoices.
6. **Price list** — baremo used to price the services. These sit at the root and are reference data, not cases.

## 3. Top-level map

| Folder or root files | Files | Size | What is stored there |
| --- | ---: | ---: | --- |
| `SCANER SEGURO MIRANDA` | 43,781 | 63.2 GB | Seguros Miranda scanner lots, carta aval cases, single invoices, and a nested CANTV 2025 archive |
| `FACTURAS` | 17,067 | 32.6 GB | Issued invoices and their page photos, grouped by account, month, and lot |
| `PREVISORA` | 4,351 | 4.1 GB | La Previsora case PDFs (`CASOS PREVISORA`, 4,170 files) plus relación workbooks |
| `SEGUROS MIRANDA` | 711 | 3.4 GB | The structured Miranda registers: 181 sábanas, 23 clave workbooks, 8 relaciones, plus some scans and invoices |
| `SEG MIRANDA NOVIEMBRE LOTE 1, PARTE 2 2026` | 997 | 1.2 GB | Loose scanner lot, 997 one-page PDFs, not filed under `SCANER SEGURO MIRANDA` |
| `SCANER SEG MIRANDA OCTUBRE LOTE 9` | 673 | 0.80 GB | Another loose scanner lot |
| `SCANER SEGUROS MIRANDA NOVIEMBRE LOTE 1 PARTE 2` | 585 | 0.69 GB | Another loose scanner lot (`Escáner_20261109 …`) |
| `SEGUROS VENEZUELA` | 567 | 0.64 GB | 32 AMP service-request `.xls` files, matching `APS nnnn.pdf` packets, and one misplaced Miranda scanner folder |
| `CORPORACION` | 168 | 0.47 GB | Cemento Andino case lots (Nov–Dec 2024), corporate invoices, one relación workbook |
| `CONSTITUCION` | 144 | 0.45 GB | Constitución / OPSU relaciones and invoice or scanner lots. One subfolder is actually SENIAT invoices |
| `CASOS SENIAT 2026` | 379 | 0.38 GB | 289 case PDFs named by person plus specialty, and 87 cintillo workbooks (one per request day) |
| `CARPETA INGENIERO` | 12 | 0.32 GB | Corporate legal file: acta constitutiva, ISLR, lease, 2024 sale. Separate from patient billing |
| `CASOS FASME CATARATAS` | 30 | 0.17 GB | Cataract case PDFs plus an October 2025 carta aval subfolder |
| `SCANER CEMENTO ANDONO MAYO 30-5-25` | 129 | 0.11 GB | Camera JPGs of a Cemento Andino batch (`IMG_00xx.JPG`) |
| `CORPOELEC` | 368 | 0.09 GB | 331 budget files (`PRESUPUESTO …`) and a few case PDFs. Small pages, so the byte count is low |
| Nine loose `FACT nnnnn …` folders | 54 | 0.26 GB | Each case is an `EGRESO` PDF plus five `IMG` PDFs, left on the root |
| `PRESUPUESTO POST OPERATORIO DE CATARATA` | 36 | 0.03 GB | Post-op cataract budgets, one PDF per person, plus one full image packet |
| `CASOS VNET` | 15 | 0.02 GB | One multi-page case PDF per person |
| `OPERADOS FASMEE CATARATAS` | 16 | 0.02 GB | Operated FASME cataract cases, one PDF per person |
| `CATARATAS` | 6 | 7 MB | Five cataract photo binders (`.pptx`) and a Windows shortcut |
| `EMERGENCIAS SENIAT EGRESOS` | 2 | 6 MB | Two emergency discharge PDFs |
| `CASOS INAC` | 2 | 0.4 MB | An invoice template workbook and a budget PowerPoint. No case files |
| Root files | 13 | 1.5 MB | Six baremos, four insumos workbooks, two insumos PDFs, one Windows shortcut |

Depth is shallow. Files sit mainly one or two folders down (1,723 at depth 1, 43,041 at depth 2, 24,605 at depth 3). A few CANTV and scanner lots go to depth 4 or 5.

## 4. Document roles by file name

Roles below are counted from the file name. Scanner pages dominate because a lot is dozens or hundreds of `Escáner_…` or `IMG_…` files. “Named case file” means the file is titled with a person’s name and no role prefix.

| Role | Files | Where it concentrates |
| --- | ---: | --- |
| Scanner page (`Escáner_`, `SCAN`, `IMG`, `IMG_`) | ~56,000 across the backup | Scanner folders and inside invoice batches |
| Named case file (person or institution) | ~8,000 | `PREVISORA/CASOS PREVISORA`, `CASOS SENIAT 2026`, `CASOS VNET`, Cemento Andino, cataracts |
| Invoice (`FACT` / `FACTURA`) | ~7,200 | `FACTURAS`, plus single-invoice folders under the scanner tree |
| Budget (`PRESUPUESTO` / `PROFORMA`) | ~340 | `CORPOELEC` (331), root baremos area, cataract budgets |
| Spreadsheet batch (`SABANA` / `FORMATO`) | ~220 | `SEGUROS MIRANDA` |
| Discharge (`EGRESO`) | ~180 | Loose root cases, scanner tree, `FACTURAS` |
| Service request (`CINTILLO`, `SOLICITUD`, AMP) | 87 cintillos + 32 AMP `.xls` | `CASOS SENIAT 2026`, `SEGUROS VENEZUELA` |
| Patient list (`RELACION`) | ~40 | `PREVISORA`, `CONSTITUCION`, `SEGUROS MIRANDA`, `CORPORACION` |
| Authorization keys (`CLAVE`) | ~24 | `SEGUROS MIRANDA` |
| Guarantee letter in the **file** name | ~10 | The carta aval **folders** are the real collection: 85 under the scanner tree |
| Fee schedule (`BAREMO`) | 8 | Root of the backup |
| Hospital supplies (`INSUMO`) | 5 | Root (3 workbooks, 2 PDFs) |
| Admission (`INGRESO`) | a handful | `FACTURAS/INGRESO JANETH AVILA` and a few Previsora files |
| Verification | a handful | `FACTURAS` and the ingreso packet |
| Tax return (`ISLR` / `ISRL`) | 7 | `CARPETA INGENIERO` |
| Account statement | 1 | `FACTURAS/ESTADO DE CUENTA 22_12_2025….xlsx` |

`FACTURAS` itself contains **443 subfolders**:

| Subfolder kind | Count |
| --- | ---: |
| Invoice batch named by account, month, and lot | 406 |
| Single invoice case (`FACT nnnnn …`) | 22 |
| Carta aval case | 4 |
| Other (Latitud, print queue, ingreso, mixed titles) | 11 |

Loose files directly inside `FACTURAS` are mostly individual `FACT nnnnn.pdf` invoices (78) plus a few discharges and the account-statement workbook.

## 5. Accounts inside `FACTURAS`

Labels were read from the folder path and assigned to one account. A folder whose title names several accounts is counted once, as mixed. Spelling variants were folded together (`CONTITUCION` with Constitución, `PIRAMIRE` with Pirámide, `LATITUC` with Latitud).

| Account label in the path | Files | Size |
| --- | ---: | ---: |
| La Previsora | 8,723 | 12.82 GB |
| Altamira | 5,063 | 6.61 GB |
| Latitud | 872 | 3.47 GB |
| Cemento Andino | 198 | 3.35 GB |
| Constitución | 775 | 1.13 GB |
| Seguros Miranda | 236 | 0.95 GB |
| SENIAT | 498 | 0.78 GB |
| Hispana | 251 | 0.68 GB |
| Unlabeled single case, print queue, or generic name | 240 | 2.07 GB |
| Pirámide | 21 | 0.22 GB |
| Seguros Venezuela | 49 | 0.20 GB |
| Mixed title (more than one account in the folder name) | 68 | 0.15 GB |
| Corporación, FASMEE, SAREN, Pueblo Soberano, Bicentenario, Cuidamed, CORPOELEC | 73 | 0.22 GB |
| **Total** | **17,067** | **32.65 GB** |

Seguros Miranda’s scans are **not** in this table. They live in `SCANER SEGURO MIRANDA` (63 GB) and in the three loose scanner folders (about 2.7 GB). `FACTURAS` holds the issued invoice images; the scanner tree holds the supporting pages.

Other accounts that have their own top-level folder rather than living under `FACTURAS`: CORPOELEC, VNET, INAC (templates only), FASME cataracts, and the legal file in `CARPETA INGENIERO`.

**CANTV is nested in the wrong place.** The 2025 CANTV monthly lots sit under:

`SCANER SEGURO MIRANDA / CARTA AVAL ANIEDYS MORENO FACT 18923 / CASOS CANTV 2025 / …`

That tree includes monthly case lots from about April through November 2025, a `FACTURAS CANTV` folder, and patient-list folders. It is a separate account archive stored inside one carta aval case.

**Contratante is a different level.** Inside Miranda sábanas the column `CONTRATANTE` is the insured’s employer or institution (values seen include CNE, BDV, ULA, UPTT, OPSU). That is not the same thing as the top-level account folder.

## 6. Structured spreadsheets

419 workbooks (387 `.xlsx` + 32 `.xls`). These are the files an ETL can read as tables. Everything else needs OCR or stays an attachment.

### 6.1 Sábana — Seguros Miranda claim register

181 files under `SEGUROS MIRANDA`, one sheet, one row per service line. Representative file: `FORMATO SABANA JUNIO LOTE 1 GPS AVILA 4.6.24.xlsx` (about 60 rows in that sample).

| Column | Field |
| --- | --- |
| A | `CLAVE RMS` |
| B | `DEPARTAMENTO O SUCURSAL` |
| C | `SERVICIO` |
| D | `FECHA RECIBIDO` |
| E | `CONTRATANTE` |
| F | `ANALISTA` |
| G | `TITULAR` |
| H | `CI TITULAR` |
| I | `BENEFICIARIO` |
| J | `CI BENEFICIARIO` |
| K | `FECHA DE NACIMIENTO` |
| L | `PARENTESCO` |
| M | `DIAGNOSTICO` |
| N | `DESCRPCION DE SERVICIOS` |
| O | `PROVEEDOR` |
| P | `MONTO DE PPTO. O MONTO FACTURADO` |
| Q | `MONTO COBERTURA SEGUROS MIRANDA` |
| R | `TASA BCV` |
| T | `MONTO BOLIVARES` |
| U | `GNA` |

Dates in the sample are Excel serial numbers (`45448`), not formatted dates. Column S is unused in the header row.

### 6.2 Claves — authorization-key register

23 files. Same population as the sábana, with coverage math and a verification flag. Header of `FORMATO CLAVES DICIEMBRE LOTE 1, 2024 GPS AVILA.xlsx`:

`CLAVE RMS`, `CONTRATANTE`, `TITULAR`, `CI TITULAR`, `BENEFICIARIO`, `CI BENEFICIARIO`, `FECHA DE NACIMIENTO`, `PARENTESCO`, `DIAGNOSTICO`, `PROVEEDOR`, `DESCRPCION DE SERVICIOS`, `MONTO COBERTURA SEGUROS MIRANDA`, `TASA BCV`, `MONTO $`, `GNA`, `EXCEDENTE`, `OBSERVACIONES`, `TELEFONO CONTACTO BENEFICIARIO (EMERGENCIAS)`, `VERIFICACION`.

Eight more workbooks are named `GPS AVILA <date>.xlsx` and follow this claves layout (`CLAVE RMS` through `TASA BCV`, plus diagnosis and service description).

### 6.3 Relación — invoice batch sent to an account

Same workbook family, reused per account. The live sheet changes; other sheets are leftovers (often a sheet still titled `SM`).

**La Previsora** sheet `S. LA PREVISORA`, header around row 10:

`FECHA DE FACTURA`, `NRO DE FACTURA`, `NRO DE CONTROL`, `FECHA DE ATENCION`, `EMPRESA /O INSTITUCION`, `TITULAR`, `CEDULA DE IDENTIDAD`, `BENEFICIARIO`, `CEDULA DE IDENTIDAD`, `PARENTESCO`, `TELEFONO`, `DIRECCION`, `DESCRIPCION DE SERVICIOS MEDICOS`, `Total`, `MONTO FACTURADO`, `CODIGO APS`, `OBSERVACIONES`.

The provider RIF is printed in the sheet header. `OBSERVACIONES` records whether the paper invoice was handed over.

**Cemento Andino** sheet `CORPORACION CEMENTO`:

`FECHA DE SERVICIO`, `FECHA FACTURA`, `NRO DE FACTURA`, `NRO DE CONTROL`, `FECHA DE ATENCION`, `EMPRESA /O INSTITUCION`, `TITULAR`, `CEDULA DE IDENTIDAD`, `BENEFICIARIO`, `CEDULA DE IDENTIDAD`, `PARENTESCO`, `TELEFONO`, `DIRECCION`, `DESCRIPCION DE SERVICIOS MEDICOS`, `Total`, `MONTO BS`, `AUTORIZACION`.

**Constitución / OPSU** (`SOLICITUD SERVICIOS OPSU …xlsx`), one sheet per month, one row per beneficiary:

`Nº`, `FECHA DE SOLICITUD`, `TITULAR`, `CEDULA DE IDENTIDAD`, `INSTITUCION`, `FECHA DE NACIMIENTO`, `BENEFICIARIO`, `CEDULA DE IDENTIDAD`, `FECHA DE NACIMIENTO`, `PARENTESCO`, `TELEFONO`, `ESTADO`.

There are 21 relación files in `PREVISORA`, 14 in `CONSTITUCION`, 8 in `SEGUROS MIRANDA`, and 1 Cemento Andino workbook.

### 6.4 Estado de cuenta

`FACTURAS/ESTADO DE CUENTA 22_12_2025 (1) (1).XLSX`, sheet `ALTAMIRA 2025` (data through row ~176):

`FECHA DE FACTURA`, `NRO DE FACTURA`, `NRO DE CONTROL`, `EMPRESA /O INSTITUCION`, `TITULAR`, `CEDULA DE IDENTIDAD`, `BENEFICIARIO`, `CEDULA DE IDENTIDAD`, `MONTO FACTURADO`, `MONTO USD`, `CODIGO APS`, `OBSERVACIONES`.

### 6.5 Cintillo — SENIAT key-commitment request

87 files, one per request day, named `CINTILLO PARA SOLICITUD <month> <dd-mm-2026>.xlsx`. Sheet `ORDENES DE SERVICIOS`. Shared labels:

`Nº`, `NOMBRE TITULAR`, `CI TITULAR`, `BENEFICIARIO`, `CI BENEFICIARIO`, `PARENTESCO`, `EDAD`, `FECHA CITA`, `TIPO DE SOLICITUD`, `SINTOMA / DIAGNOSTICO`, `TELF.ASEGURADO`, `ESTADO`, `RAZON SOCIAL`, `RIF`, `BAREMO APROBADO`, `MONTO USD`, `DIRECCION`, `OPERADOR`, `NRO DE COMPROMISOS DE CLAVE`.

The sheet title is `RELACION DE SOLICITUD DE COMPROMISOS DE CLAVE`, headed with the GPS Avila legal name and the Trujillo address. Each workbook also embeds images, so part of a cintillo may be a picture of the form rather than cells.

### 6.6 AMP servicio inmediato — Seguros Venezuela

32 files, `AMP (SERVICIO INMEDIATO) APS 40xx.xls`, Excel 97–2003, last saved by “Gps Avila”. Labels recovered from the workbook:

`NOMBRE DEL TITULAR`, `C.I. TITULAR`, `NOMBRE DEL PACIENTE`, `C.I. PACIENTE`, `PARENTESCO`, `CLAVE DE AUTORIZACIÓN`, `FECHA DE LA CITA`, `FECHA DEL DIA DE LA SOLICITUD`, `DIAGNÓSTICO`, `NOMBRE DEL PROVEEDOR`, `RIF. DEL PROVEEDOR`, `MONTO TOTAL SOLICITADO`, `MONTO AUTORIZADO`, `MONTO SOLICITADO POR EL CENTRO`.

Parentesco codes printed in the form: `T` titular, `C` cónyuge, `H` hijo, `Hno.` hermano, `M` madre, `P` padre. Amount formats in the file are bolívares (`Bs.`, `Bs.S`). The provider line is G.P.S. Gestión Profesional de Salud Avila, C.A. Matching `APS 40xx.pdf` files sit beside these workbooks.

### 6.7 Baremos — price lists

Reference data at the root, not case rows.

| File | Sheets and columns |
| --- | --- |
| `Baremos Seguros Miranda Contrapropuesta.xlsx` | `CODIGO`, `DESCRIPCION`, `CATEGORIA`, `BAREMO REF SM` (example code `CON-0011`) |
| `BAREMOS GPS- FORMATO SENIAT 2025 CONTRA OFERTA.XLSX` and `PLANTILLA REFERENCIAL SASS PARA PROVEEDORES.XLSX` | `CODIGO`, `DESCRIPCION`, `COSTOS $`, plus contraoferta columns. A second sheet, `DESGLOSE DE PERFIL`, lists lab-profile contents (`PERFIL 20`, and so on) |
| `BAREMO APS PREVISORA 2025 CORREGIDO.xlsx` | `CONSULTAS Y PROCEDIMIENTOS` (`CODIGO`, `CONSULTAS`, `TIPO DE SERVICIO`, `COSTOS PREVISORA MARZO EN DOLARES`, `EQUIVALE 9,10%`, `PRECIO ACTUALIZADO`), `LABORATORIOS`, `IMAGENOLOGIA` |
| `BAREMOS CORPORACION 2025.xlsx` | `CONSULTA APS`, `CONSULTA EMERGENCIA`, `PROCEDIMIENTOS AMB`, `ESTUDIOS`, `LABORATORIOS`, `QUIRURGICO`, `UCI - EMERGENCIA`. Columns compare `BAREMO UNICO 2024 PAGO $` with `PROPUESTA 2025 PAGO $` |
| `BAREMO  GPS AVILA CONTRA OFERTA.XLSX` | `SERVICIO`, `TIPO`, `PRECIO USD`, with a contraoferta column. Headered as provider GPS Avila, región occidente |

### 6.8 Invoice and supply templates

`FORMATO INSUMOS DE HOSPITALIZACION….xlsx` (and the two PDF copies) is a **template book**, 24 sheets, one layout per client: `FACTURA UVM`, `FACTURA HAZ MEDICA`, `NOTA DE ENTREGA PALPITAR`, `FACTURA CEMENTO ANDINO`, `FACTURA LATITUD`, `FACTURA CAMARA MUNICIPAL`, `FACTURA SM`, `PRESUPUESTO PREVISORA`, and others. The same template is copied into `CORPOELEC/PRESUPUESTO CORPOELEC.xlsx`, `CASOS INAC/FORMATO FACTURA.xlsx`, and `PREVISORA/FORMATO FACTURA.xlsx`.

Line fields: `Cod. Sis`, `Servicio`, `Cant.`, `Precio Unitario`, `Total Neto`, `Forma de Pago`, `Monto Bs.`, `Titular`, `Beneficiario`, `Cedula`, `CODIGO CLIENTE`, `Nº FACTURA`, `FECHA DE EMISION`, `Sub Total`, `IVA (16%)`, `Total`. Service codes in the template use prefixes `CN-` (consult), `LB-` (lab), `RX-` (X-ray), `PE-` (exam package), `PAE-`, `US-`. One sheet is a materials breakdown (`DESGLOSE DE MATERIALES Y MEDICINAS`: tegaderm, gasas, jeringas, and similar).

`CORPOELEC` also has per-person `PRESUPUESTO <name>.xlsx` files (13 workbooks) plus hundreds of budget PDFs.

## 7. What one case looks like

A finished case is a small set of files, repeated hundreds of times:

| Piece | Typical name | Format |
| --- | --- | --- |
| Discharge | `EGRESO <person>.pdf` | Multi-page PDF, often a PowerPoint export |
| Supporting pages | `IMG 021.pdf` … or `IMG_0001.JPG` plus a PDF twin | One scan per file. The loose root cases use five IMG PDFs |
| Invoice | `FACT <number> <person> <cedula>.pdf` | Single document; the number is the invoice id |
| Guarantee letter | folder `CARTA AVAL <person> FACT <number>` | PPTX binder and a PDF export of the same binder |
| Batch line | one row in that lot’s sábana or relación | The only normalized record |

`FACT 24429 MARIBEL CACERES` on the root is the pattern: 1 egreso PDF + 5 image PDFs. `PRESUPUESTO POST OPERATORIO DE CATARATA/FACT 21575 ANDREINA RIVAS` is the same packet with both JPG and PDF for each page.

Previsora cases are usually one PDF per person or per APS number (`APS 5909.pdf`, 5 pages, exported from PowerPoint). SENIAT cases are one PDF per person with a specialty suffix (`OFT`, `HC+ FROTIS`).

## 8. Keys an ETL can trust, and keys it cannot

Present and usable once the spreadsheets are parsed:

| Key | Where |
| --- | --- |
| Invoice number | `FACT nnnnn` in names; `NRO DE FACTURA` in relaciones and the estado de cuenta |
| Control number | `NRO DE CONTROL` |
| RMS key | `CLAVE RMS` in sábanas and clave workbooks |
| APS code | `CODIGO APS` in Previsora relaciones and the Altamira estado de cuenta |
| Service code | Baremo `CODIGO` (`CON-`, `ALER-`, `LAB-`) and template codes (`CN-`, `LB-`, `RX-`, `PE-`) |
| Identity document | `CI TITULAR` / `CEDULA DE IDENTIDAD`, stored with or without dots |
| Lot identity | month + year + `LOTE` + optional `PARTE` in the folder name |

Not safe to treat as already clean:

- **Dates.** Many are Excel serials. Folder years such as 2043 or 2056 are invoice numbers that happen to start with 20, not calendar years. Real year tokens in folder names are 2024, 2025, and 2026.
- **One person, many files.** The same invoice is often a PDF, a JPG, and a slide in a PPTX, and may also be a row in a sábana.
- **The two `.rar` files** duplicate October 2026 scanner lots already expanded as PDFs.
- **Processed is a folder move**, not a flag on the row.
- **Text search on scans will miss the content.** Scanner PDFs and PowerPoint-export PDFs have no text layer.
- **Account is the folder name**, with the spelling drift listed above. A few folders name two accounts at once.
- **CANTV’s 2025 archive is filed under a single carta aval.** Loading “everything under Seguros Miranda” will pull CANTV in with it.
- **`SEGUROS VENEZUELA` contains a Seguros Miranda scanner folder** (`SCANER SEGURO MIRANDA AGOSTO LOTE 4, 2026, PARTE 2`).
- **`CONSTITUCION/FACTURA SENIAT AGOSTO LOTE 2, 2026`** is a SENIAT invoice lot stored under Constitución.
- **Shortcuts, `desktop.ini`, and the empty `.tmp`** are not records.
- **`CARPETA INGENIERO`** is corporate tax and legal material (ISLR, lease, acta constitutiva). It should stay out of the clinical model.

## 9. Suggested logical model

If this backup is loaded, the natural entities are:

| Entity | Source | Grain |
| --- | --- | --- |
| `account` | Top-level folder and the account token in batch titles | One per payer or corporate client |
| `batch` | Folder with month, year, lote, parte | One delivery lot |
| `case` | `FACT` number, or person name when no invoice number exists | One episode of care |
| `document` | Each PDF, JPG, PNG, PPTX | One file, typed by the role prefix, linked to the case |
| `service_line` | One row of a sábana, claves sheet, relación, cintillo, or AMP sheet | One billable line |
| `fee` | One row of a baremo | One priced service code, per account and year |
| `workflow_state` | `procesadas` / `listas` / `digitalizaciones` in the path | Attribute of the document or the batch |

The join between a scanned page and a service line is the invoice number or the RMS key. Pages named only `Escáner_… (n)` have **no key inside the file name**; they belong to the batch folder and have to be matched by OCR or by the order they were scanned.

---

Counts come from a full walk of `Avila-backup` on 13 November 2026. Spreadsheet columns come from the header row of the representative workbooks named above. Folder labels were normalized only for the account table in section 5; everywhere else the names are the names on disk.
