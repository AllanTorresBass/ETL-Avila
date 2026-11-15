# Avila-backup invoice inventory

File-level classification of `Avila-backup`. A fiscal invoice here is a file named as the billed document (`FACT`, `FAC`, or `FACTURA`), not a clinical page stored beside it. Scanner pages inside a folder whose title carries a `FACT` range are candidates: the folder proves the batch is invoices, and the page pass decides which images are the fiscal sheet.

This summary has counts and invoice numbers only. Paths, which can contain patient names, are in `invoices.csv`.

## Counts

| Measure | Value |
| --- | ---: |
| Files classified | 70,092 |
| Sidecars omitted (shortcuts, temp files, archives) | 39 |
| Invoice packets | 7,200 |
| Candidate pages awaiting the page pass | 9,484 |
| Supporting documents that mention an invoice | 564 |
| Templates | 11 |
| Not an invoice | 52,833 |
| Invoice-packet bytes | 33.70 GB |
| Packets with a known page count | 7,157 |
| Average pages in those packets | 6.8 |
| Distinct invoice numbers on named packets | 6,884 |
| Invoice numbers stored as more than one file | 258 |

| Label | Files | GB |
| --- | --- | --- |
| invoice_packet | 7,200 | 33.70 |
| needs_page_check | 9,484 | 10.29 |
| supporting | 564 | 6.15 |
| template | 11 | 0.00 |
| not_invoice | 52,833 | 57.06 |

## Why a file was labeled

Rules run in order: skip junk, then templates, then a clinical or register role, then a named invoice, then an unnamed scan whose folder title contains a `FACT` number. `default_not_invoice` and `scan_outside_invoice` are the rest of the backup and are omitted from this table.

| Rule | Files |
| --- | --- |
| scan_in_fact_batch | 9,483 |
| named_fact_number | 7,148 |
| role_presupuesto | 342 |
| role_egreso | 201 |
| role_sabana | 183 |
| role_cintillo | 87 |
| role_relacion | 40 |
| named_fact_word_folder_number | 38 |
| role_carta_aval | 12 |
| template_not_issued | 11 |
| role_ingreso | 9 |
| role_baremo | 8 |
| named_fac_number | 7 |
| named_fact_word | 6 |
| gpspdf_bundle | 1 |
| named_fact_multi | 1 |

## Invoice packets

Confidence is `high` when the file name itself contains `FACT` plus a number, and `medium` for `FAC` or for a `FACT` word whose number comes from the folder.

| Confidence | Packets |
| --- | --- |
| high | 7,148 |
| medium | 52 |

| Extension | Packets |
| --- | --- |
| .pdf | 6,891 |
| .pptx | 211 |
| .potx | 55 |
| .jpg | 33 |
| .png | 9 |
| .ppt | 1 |

| Channel | Packets |
| --- | --- |
| FACTURAS | 6,824 |
| SCANER SEGURO MIRANDA | 252 |
| SEGUROS MIRANDA | 52 |
| CONSTITUCION | 35 |
| PREVISORA | 27 |
| CORPORACION | 5 |
| CASOS FASME CATARATAS | 4 |
| CORPOELEC | 1 |

| Account token in the path | Packets |
| --- | --- |
| La Previsora | 3,183 |
| Altamira | 1,136 |
| Latitud | 869 |
| Seguros Miranda | 532 |
| Constitucion | 395 |
| SENIAT | 325 |
| Hispana | 241 |
| Cemento Andino | 195 |
| (no account token) | 107 |
| mixed | 95 |
| Seguros Venezuela | 32 |
| FASMEE | 25 |
| Corporacion | 24 |
| Piramide | 19 |
| SAREN | 12 |
| CORPOELEC | 6 |
| Bicentenario | 2 |
| Cuidamed | 2 |

| Year token | Packets |
| --- | --- |
| (no year) | 1,897 |
| 2024 | 702 |
| 2025 | 2,750 |
| 2026 | 1,851 |

`mixed` means the folder title names more than one account. The original title is in the `account_raw` column of the CSV.

## Candidate pages

These files are not labeled invoices. They are `IMG` or `Escáner` pages, or a `GPSPDF` bundle, sitting under a folder title that contains a `FACT` number or range. One number is not assigned to each page.

| Rule | Files |
| --- | --- |
| scan_in_fact_batch | 9,483 |
| gpspdf_bundle | 1 |

## Duplicates

The same invoice number on a PDF and a PowerPoint, including a copy under `procesadas`, shares one `duplicate_group` (`fact-<number>`). Groups with more than one file: 258.

## What this file pass does not decide

Named packets are usually multi-page image binders exported from PowerPoint, with no text layer. The packet is the invoice file. Which pages inside it are the fiscal sheet is the page pass (`invoice-pages.csv`). Candidate scans in a `FACT 18653-18819` style folder are the same problem: several images per invoice, so the range stays on the folder and the page stays unnumbered until OCR.

## Page pass

OCR (Spanish Tesseract, 120 DPI) ran on invoice packets and on scans whose folder title contains a `FACT` number. A page is the fiscal sheet when the text has `FACTURA` together with a fiscal token, when `N° DE CONTROL` appears with the forma libre markers, or when the page carries the forma libre title or the crédito fiscal footer. Comprobantes, informes, and pages that only repeat a RIF stay attachments. PowerPoint packets are read from the photograph on each slide. The one binary `.ppt` file is left unreadable.

| Page label | Pages |
| --- | ---: |
| Fiscal invoice sheet | 9,473 |
| Attachment | 49,827 |
| Unreadable | 87 |

Evidence in `invoice-pages.csv` names the matched tokens. It does not copy the page text.
