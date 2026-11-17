"""Path-string tests for invoice classification. No backup files are opened."""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    classify_document,
    extract_all_cedulas,
    extract_identity_number,
    extract_personal_identity,
    extract_titular_from_ocr,
    extract_titular_from_path,
)
from invoice_pages import judge_page
from invoice_rules import classify
from ocr_invoice_pages import _render_office


class InvoiceRuleTests(unittest.TestCase):
    def test_named_fact_pdf_is_invoice_packet(self):
        result = classify(
            "FACTURAS/FACTURAS PREVISORA NOVIEMBRE LOTE 1, 2024/FACT 9351.pdf"
        )
        self.assertEqual(result.label, "invoice_packet")
        self.assertEqual(result.rule_id, "named_fact_number")
        self.assertEqual(result.invoice_number, "9351")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.account, "La Previsora")
        self.assertEqual(result.month, "NOVIEMBRE")
        self.assertEqual(result.year, "2024")
        self.assertEqual(result.lote, "1")
        self.assertEqual(result.duplicate_group, "fact-9351")
        self.assertEqual(result.channel, "FACTURAS")

    def test_egreso_mentioning_fact_is_supporting(self):
        result = classify(
            "SCANER SEGURO MIRANDA/FACT 20863 EJEMPLO/EGRESO EJEMPLO FACT 20863.pdf"
        )
        self.assertEqual(result.label, "supporting")
        self.assertEqual(result.rule_id, "role_egreso")
        self.assertEqual(result.related_invoice_number, "20863")
        self.assertEqual(result.invoice_number, "")
        self.assertEqual(result.duplicate_group, "")

    def test_engreso_typo_is_supporting(self):
        result = classify("FACTURAS/ENGRESO EJEMPLO FACT 1000.pdf")
        self.assertEqual(result.label, "supporting")
        self.assertEqual(result.related_invoice_number, "1000")

    def test_carta_aval_file_is_supporting(self):
        result = classify(
            "SCANER SEGURO MIRANDA/CARTA AVAL FACT 20434 EJEMPLO/CARTA AVAL EJEMPLO.pdf"
        )
        self.assertEqual(result.label, "supporting")
        self.assertEqual(result.rule_id, "role_carta_aval")

    def test_fact_file_inside_carta_aval_folder_is_invoice(self):
        result = classify(
            "SCANER SEGURO MIRANDA/CARTA AVAL EJEMPLO FACT 19775/FACT EJEMPLO.pdf"
        )
        self.assertEqual(result.label, "invoice_packet")
        self.assertEqual(result.invoice_number, "19775")
        self.assertEqual(result.rule_id, "named_fact_word_folder_number")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.duplicate_group, "fact-19775")

    def test_img_in_fact_range_folder_is_candidate_without_a_number(self):
        result = classify(
            "FACTURAS/FACTURA PREVISORA ABRIL LOTE 3, 2026 FACT 18653-18819/IMG_0001.JPG"
        )
        self.assertEqual(result.label, "needs_page_check")
        self.assertEqual(result.rule_id, "scan_in_fact_batch")
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.invoice_number, "")
        self.assertEqual(result.invoice_range, "18653-18819")
        self.assertEqual(result.account, "La Previsora")
        self.assertEqual(result.month, "ABRIL")
        self.assertEqual(result.year, "2026")
        self.assertEqual(result.lote, "3")

    def test_scan_page_number_not_assigned_per_file(self):
        first = classify(
            "FACTURAS/LOTE FACT 1000-1002/IMG_0001.JPG"
        )
        second = classify(
            "FACTURAS/LOTE FACT 1000-1002/IMG_0002.JPG"
        )
        self.assertEqual(first.invoice_number, "")
        self.assertEqual(second.invoice_number, "")
        self.assertEqual(first.invoice_range, second.invoice_range)

    def test_scanner_lot_without_fact_number_is_not_invoice(self):
        result = classify(
            "SCANER SEGURO MIRANDA/SCANER LOTE/Escáner_20261109 (106).pdf"
        )
        self.assertEqual(result.label, "not_invoice")
        self.assertEqual(result.rule_id, "scan_outside_invoice")

    def test_formato_factura_workbook_is_template(self):
        result = classify("PREVISORA/FORMATO FACTURA.xlsx")
        self.assertEqual(result.label, "template")
        self.assertEqual(result.rule_id, "template_not_issued")

    def test_insumos_workbook_is_template(self):
        result = classify("FORMATO INSUMOS DE HOSPITALIZACION 25-3-2025.xlsx")
        self.assertEqual(result.label, "template")
        self.assertEqual(result.channel, "(root)")

    def test_fac_without_t_is_medium_confidence(self):
        result = classify("FACTURAS/LATITUD/FAC 5580.pdf")
        self.assertEqual(result.label, "invoice_packet")
        self.assertEqual(result.rule_id, "named_fac_number")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.invoice_number, "5580")
        self.assertEqual(result.account, "Latitud")
        self.assertEqual(result.duplicate_group, "fact-5580")

    def test_same_number_shares_duplicate_group_across_extensions(self):
        pdf = classify("FACTURAS/ALTAMIRA/procesadas/FACT 14029.pdf")
        pptx = classify("FACTURAS/ALTAMIRA/FACT 14029.pptx")
        self.assertEqual(pdf.duplicate_group, "fact-14029")
        self.assertEqual(pptx.duplicate_group, pdf.duplicate_group)
        self.assertEqual(pdf.workflow, "procesadas")
        self.assertEqual(pptx.workflow, "")
        self.assertEqual(pdf.account, "Altamira")

    def test_mixed_account_title_is_kept(self):
        result = classify(
            "FACTURAS/LATITUD , CONSTITUCION, SEG. VENEZUELA/FACT 1000.pdf"
        )
        self.assertEqual(result.account, "mixed")
        self.assertIn("Latitud", result.account_labels)
        self.assertIn("Constitucion", result.account_labels)
        self.assertIn("Seguros Venezuela", result.account_labels)
        self.assertIn("LATITUD", result.account_raw.upper())

    def test_two_ranges_stay_a_range(self):
        result = classify(
            "FACTURAS/HISPANA LOTE 2 FACT 16883-16908 y 16979-16992/IMG_0003.JPG"
        )
        self.assertEqual(result.label, "needs_page_check")
        self.assertEqual(result.invoice_number, "")
        self.assertEqual(result.invoice_range, "16883-16908;16979-16992")
        self.assertEqual(result.account, "Hispana")

    def test_multi_number_filename_is_not_one_invoice(self):
        result = classify("FACTURAS/PREVISORA/FACT 13813 Y FACT 13815.pdf")
        self.assertEqual(result.label, "invoice_packet")
        self.assertEqual(result.rule_id, "named_fact_multi")
        self.assertEqual(result.invoice_number, "")
        self.assertEqual(result.invoice_numbers, "13813;13815")
        self.assertEqual(result.duplicate_group, "")

    def test_baremo_is_not_an_invoice(self):
        result = classify("BAREMOS CORPORACION 2025.xlsx")
        self.assertEqual(result.label, "not_invoice")
        self.assertEqual(result.rule_id, "role_baremo")

    def test_sabana_is_not_an_invoice(self):
        result = classify(
            "SEGUROS MIRANDA/FORMATO SABANA JUNIO LOTE 1 GPS AVILA 4.6.24.xlsx"
        )
        self.assertEqual(result.label, "not_invoice")
        self.assertEqual(result.rule_id, "role_sabana")
        self.assertEqual(result.month, "JUNIO")
        self.assertEqual(result.lote, "1")

    def test_person_case_pdf_is_not_an_invoice(self):
        result = classify("PREVISORA/CASOS PREVISORA/APS 5909.pdf")
        self.assertEqual(result.label, "not_invoice")
        self.assertEqual(result.account, "La Previsora")

    def test_gpspdf_bundle_needs_page_check(self):
        result = classify(
            "FACTURAS/FACT 18653-18819/GPSPDF_260424_165950.pdf"
        )
        self.assertEqual(result.label, "needs_page_check")
        self.assertEqual(result.rule_id, "gpspdf_bundle")
        self.assertEqual(result.invoice_number, "")

    def test_shortcut_is_skipped(self):
        result = classify("Disco local (C) - Acceso directo.lnk")
        self.assertEqual(result.rule_id, "skipped_sidecar")

    def test_spelling_variants(self):
        self.assertEqual(classify("FACTURAS/PREVISA/FACT 1000.pdf").account, "La Previsora")
        self.assertEqual(classify("FACTURAS/LATITUC/FACT 1000.pdf").account, "Latitud")
        self.assertEqual(
            classify("FACTURAS/CONTITUCION/FACT 1000.pdf").account, "Constitucion"
        )
        self.assertEqual(classify("FACTURAS/PIRAMIRE/FACT 1000.pdf").account, "Piramide")
        self.assertEqual(
            classify("FACTURAS/ANDONO CEMENTO/FACT 1000.pdf").account, "Cemento Andino"
        )

    def test_procesadas_nest_still_sees_fact_range(self):
        result = classify(
            "FACTURAS/ALTAMIRA FACT 100-120/procesadas/IMG_0004.JPG"
        )
        self.assertEqual(result.label, "needs_page_check")
        self.assertEqual(result.workflow, "procesadas")
        self.assertEqual(result.invoice_range, "100-120")

    def test_lote_roman_numeral(self):
        result = classify("PREVISORA/RELACION ABRIL LOTE II.xlsx")
        self.assertEqual(result.lote, "II")
        self.assertEqual(result.rule_id, "role_relacion")


class PageJudgeTests(unittest.TestCase):
    def test_heading_with_control_and_rif_is_fiscal(self):
        text = "FACTURA\nN° DE FACTURA 000123\nNRO DE CONTROL 00-000123\nRIF J-410292814"
        label, evidence = judge_page(text)
        self.assertEqual(label, "fiscal_invoice")
        self.assertIn("heading:FACTURA", evidence)
        self.assertIn("control", evidence)
        self.assertNotIn("000123", evidence)

    def test_egreso_page_is_attachment(self):
        label, evidence = judge_page("EGRESO\nLABORATORIO")
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "clinical_terms")

    def test_empty_ocr_is_unreadable(self):
        self.assertEqual(judge_page("   "), ("unreadable", "empty_ocr"))

    def test_heading_alone_is_not_enough(self):
        label, evidence = judge_page("FACTURA\nsin numero fiscal")
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "heading_without_fiscal_token")

    def test_forma_libre_without_a_readable_factura_word(self):
        text = "N° DE CONTROL 00-011746 FORMA LIBRE ORIGINAL RIF J-410292814"
        label, evidence = judge_page(text)
        self.assertEqual(label, "fiscal_invoice")
        self.assertIn("control", evidence)
        self.assertIn("forma", evidence)

    def test_authorization_slip_is_not_the_invoice(self):
        text = "COMPROBANTE DE AUTORIZACION DE SERVICIO RIF J-302020476"
        label, evidence = judge_page(text)
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "comprobante")

    def test_preliquidacion_that_cites_a_factura_is_not_the_invoice(self):
        text = "COMPROBANTE DE PRELIQUIDACION\nN° Factura: 00011197\nN° Control: 00-011197"
        label, evidence = judge_page(text)
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "comprobante")

    def test_glued_control_token_still_marks_forma_libre(self):
        text = "N  DECONTROL FORMA IRE\nORIGINAL BLANCA\nRIF J-410292814"
        label, evidence = judge_page(text)
        self.assertEqual(label, "fiscal_invoice")
        self.assertIn("control", evidence)
        self.assertIn("forma", evidence)

    def test_medical_report_with_only_a_rif_is_not_the_invoice(self):
        label, evidence = judge_page("INFORME MEDICO\nRIF J-410292814")
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "informe")

    def test_credito_fiscal_footer_is_the_invoice(self):
        label, evidence = judge_page("ESTE DOCUMENTO NO DA DERECHO A CRÉDITO FISCAL")
        self.assertEqual(label, "fiscal_invoice")
        self.assertEqual(evidence, "credito_fiscal")

    def test_forma_libre_title_without_control_is_the_invoice(self):
        label, evidence = judge_page("FORMA LIBRE\nRIF J-410292814")
        self.assertEqual(label, "fiscal_invoice")
        self.assertEqual(evidence, "forma_libre")

    def test_glued_decontrol_without_forma_is_the_invoice(self):
        label, evidence = judge_page("N  DECONTROL 00-0009351\nRIF J-410292814")
        self.assertEqual(label, "fiscal_invoice")
        self.assertEqual(evidence, "decontrol")

    def test_letterhead_rif_alone_is_not_the_invoice(self):
        label, evidence = judge_page("GESTION PROFESIONAL DE SALUD\nRIF J-410292814")
        self.assertEqual(label, "attachment")
        self.assertEqual(evidence, "no_factura_heading")


class DocumentTypeTests(unittest.TestCase):
    def test_fiscal_page_maps_to_factura(self):
        dtype, _ = classify_document("FACTURA N° 000123\nN° DE CONTROL 00-000123\nRIF J-410292814")
        self.assertEqual(dtype, "factura_fiscal")

    def test_cedula_card_maps(self):
        dtype, evidence = classify_document(
            "REPUBLICA BOLIVARIANA DE VENEZUELA\nCEDULA DE IDENTIDAD\n"
            "APELLIDOS PEREZ\nNOMBRES JUAN\nV-12.345.678\nVENEZOLANO"
        )
        self.assertEqual(dtype, "cedula_identidad")
        self.assertEqual(evidence, "cedula_card")

    def test_siniestro_form_is_not_cedula(self):
        dtype, _ = classify_document(
            "DECLARACION DE SINIESTRO DE HCM\nDATOS DEL TITULAR\n"
            "JUAN JOSE PEREZ\nBENEFICIARIO LUIS PEREZ\nREPUBLICA BOLIVARIANA"
        )
        self.assertNotEqual(dtype, "cedula_identidad")

    def test_carnet_bdv_maps(self):
        dtype, evidence = classify_document(
            "BANCO DE VENEZUELA\nJuan J. Perez A.\n11.222.333\nVP Servicios\nCARNET"
        )
        self.assertEqual(dtype, "carnet")
        self.assertEqual(evidence, "carnet_bdv")

    def test_id_collage_sheet_maps(self):
        dtype, evidence = classify_document(
            "Gestión Profesional de Salud Ávila, C.A\nDOCUMENTOS DE IDENTIFICACION\n"
            "PEREZ GOMEZ\nJuan J. Perez A.\n11.222.333\nVP Servicios\nBDV"
        )
        self.assertEqual(dtype, "documentos_identificacion")
        self.assertEqual(evidence, "documentos_identificacion")

    def test_id_collage_with_ocr_noise_between_words_maps(self):
        dtype, _ = classify_document(
            "Gestión Profesional de Salud Ávila, C.A\npl a DOCUMENTOS DE\n"
            "aa a En > IDENTIFICACION\nPBDV\nJuan J. Perez A.",
            backup_path="SCANER SEGURO MIRANDA/CARTA AVAL/FACT 12345 ANA PEREZ.pdf",
        )
        self.assertEqual(dtype, "documentos_identificacion")

    def test_solicitud_carta_aval_form_is_not_cedula(self):
        dtype, evidence = classify_document(
            "Gobierno Bolivariano de Venezuela\nSOLICITUD CARTA AVAL\n"
            "Apellidos y Nombres del Titular Cédula de identidad/RIF\n"
            "Juan Perez 11222333\nInforme Médico (Indicando Diagnóstico)"
        )
        self.assertEqual(dtype, "carta_aval")
        self.assertEqual(evidence, "solicitud_carta_aval")

    def test_acta_nacimiento_not_cedula(self):
        dtype, evidence = classify_document(
            "REPÚBLICA BOLIVARIANA DE VENEZUELA\nCONSEJO NACIONAL ELECTORAL\n"
            "COMISIÓN DE REGISTRO CIVIL Y ELECTORAL\nREGISTRO CIVIL MUNICIPAL\n"
            "UNIDAD DE REGISTRO CIVIL HOSPITALARIO\nActa N° 08\n"
            "LUIS ANDRES PEREZ DIAZ\nJUAN JOSE PEREZ GOMEZ\n"
            "titular de la Cedula de identidad N° V-11.222.333\nVENEZOLANA"
        )
        self.assertEqual(dtype, "acta_nacimiento")
        self.assertEqual(evidence, "acta_nacimiento")

    def test_plastic_cedula_still_maps_when_no_acta(self):
        dtype, evidence = classify_document(
            "REPUBLICA BOLIVARIANA DE VENEZUELA\nCEDULA DE IDENTIDAD\n"
            "APELLIDOS PEREZ GOMEZ\nNOMBRES JUAN JOSE\n"
            "V-11.222.333\nVENEZOLANO\nF. EXPEDIC 02-2024"
        )
        self.assertEqual(dtype, "cedula_identidad")
        self.assertEqual(evidence, "cedula_card")

    def test_siniestro_with_pasaporte_label_is_comprobante(self):
        dtype, evidence = classify_document(
            "REPUBLICA BOLIVARIANA DE VENEZUELA\nDECLARACION DE SINIESTRO\n"
            "NOMBRE DEL ASEGURADO\nC.I. O PASAPORTE V-12345678\nDIAGNOSTICO"
        )
        self.assertEqual(dtype, "comprobante")
        self.assertEqual(evidence, "declaracion_siniestro")

    def test_passport_card_still_maps(self):
        dtype, _ = classify_document(
            "REPUBLICA BOLIVARIANA DE VENEZUELA\nPASAPORTE\nAPELLIDOS PEREZ\nNOMBRES JUAN"
        )
        self.assertEqual(dtype, "pasaporte")

    def test_bare_registro_civil_in_informe_is_not_acta(self):
        dtype, _ = classify_document(
            "INFORME MEDICO\nPaciente recien nacido, registro civil de Caracas"
        )
        self.assertNotEqual(dtype, "acta_nacimiento")

    def test_registro_civil_with_presentante_is_acta(self):
        dtype, _ = classify_document(
            "REGISTRO CIVIL MUNICIPAL\nEl presentante declara\nFOLIO 12"
        )
        self.assertEqual(dtype, "acta_nacimiento")

    def test_egreso_from_path(self):
        dtype, _ = classify_document("texto clinico", backup_path="FACTURAS/EGRESO EJEMPLO FACT 1000.pdf")
        self.assertEqual(dtype, "egreso")

    def test_comprobante_maps(self):
        dtype, _ = classify_document("COMPROBANTE DE AUTORIZACION\nRIF J-302020476")
        self.assertEqual(dtype, "comprobante")

    def test_claim_form_with_factura_box_is_not_fiscal(self):
        text = "DECLARACION DE SINIESTRO\nFACTURA N° 12345\nRIF J-123456789\nNOMBRE DEL ASEGURADO"
        self.assertEqual(judge_page(text), ("attachment", "claim_form"))
        dtype, _ = classify_document(text)
        self.assertEqual(dtype, "comprobante")

    def test_truncated_siniestro_and_reclamo_letter_are_not_fiscal(self):
        self.assertEqual(judge_page("LARACION DE SINIESTRO DE HCM N*001 478\nFACTURA N 12")[0], "attachment")
        self.assertEqual(
            judge_page("SEGUROS EJEMPLO NRO PPTO/FACTURA: N/A\nNO.RECLAMO: 1234567\nNO.CLAVE: 1234567")[0],
            "attachment",
        )

    def test_insurer_carta_aval_letter_is_carta_aval(self):
        text = (
            "Nro Póliza: 1234 Seguros Ejemplo Nro Ppto/Factura: N/A CARTA AVAL\n"
            "Fecha Emisión: 01/02/2025 Señores G.P.S. GESTION PROFESIONAL DE SALUD"
        )
        self.assertEqual(classify_document(text), ("carta_aval", "carta_aval_letter"))

    def test_siniestro_with_carta_aval_checkbox_stays_comprobante(self):
        text = "LARACION DE SINIESTRO DE HCM\n[ ] Clave de Emergencia [x] Carta Aval\nFACTURA N 12"
        self.assertEqual(classify_document(text), ("comprobante", "declaracion_siniestro"))

    def test_solicitud_carta_aval_with_factura_word_is_not_fiscal(self):
        label, _ = judge_page("SOLICITUD DE CARTA AVAL\nNRO FACTURA\nRIF J-123456789")
        self.assertEqual(label, "attachment")

    def test_real_fiscal_sheet_still_fiscal(self):
        label, _ = judge_page("FACTURA\nN° DE CONTROL 00-1234\nRIF J-123456789\nFORMA LIBRE")
        self.assertEqual(label, "fiscal_invoice")

    def test_patient_report_with_aps_footer_is_informe(self):
        dtype, evidence = classify_document(
            "NOMBRE DEL PACIENTE: JUAN PEREZ\nEDAD 40\nDIAGNOSTICO: GRIPE\nAPS Ávila"
        )
        self.assertEqual((dtype, evidence), ("informe_medico", "patient_report"))

    def test_titled_service_order_stays_orden(self):
        dtype, _ = classify_document(
            "ORDEN DE SERVICIO\nNOMBRE DEL PACIENTE: JUAN PEREZ\nDIAGNOSTICO: GRIPE\nAPS"
        )
        self.assertEqual(dtype, "orden_servicio")

    def test_bare_aps_slip_is_orden(self):
        dtype, _ = classify_document("APS\nAUTORIZADO\nCONSULTA")
        self.assertEqual(dtype, "orden_servicio")

    def test_cedula_plus_bdv_carnet_untitled_is_collage(self):
        dtype, evidence = classify_document(
            "REPUBLICA BOLIVARIANA DE VENEZUELA\nCEDULA DE IDENTIDAD\nAPELLIDOS PEREZ\n"
            "NOMBRES JUAN\nV-11.222.333\nBANCO DE VENEZUELA\nVP Servicios\nCARNET"
        )
        self.assertEqual((dtype, evidence), ("documentos_identificacion", "collage_untitled"))

    def test_solicitud_checklist_mentioning_carnet_is_carta_aval(self):
        dtype, _ = classify_document(
            "SOLICITUD DE CARTA AVAL\nRequisitos: Informe Médico, copia del CARNET\nDiagnóstico"
        )
        self.assertEqual(dtype, "carta_aval")

    def test_carta_aval_folder_is_last_resort(self):
        path = "SCANER/CARTA AVAL/FACT 12345 ANA PEREZ.pdf"
        self.assertEqual(classify_document("texto sin pistas", backup_path=path), ("carta_aval", "carta_aval_folder"))
        self.assertEqual(classify_document("PRESUPUESTO\nTOTAL", backup_path=path)[0], "presupuesto")
        self.assertEqual(classify_document("RAYOS X TORAX", backup_path=path)[0], "imagenologia")

    def test_extract_cedula_digits(self):
        found = extract_identity_number("CEDULA DE IDENTIDAD\nV-12345678\nNOMBRE")
        self.assertEqual(found, ("cedula", "12345678"))

    def test_extract_dotted_cedula(self):
        self.assertEqual(
            extract_identity_number("C.I. N° V-11.222.333"), ("cedula", "11222333")
        )

    def test_word_ending_in_v_or_e_is_not_cedula(self):
        self.assertIsNone(extract_identity_number("TELEFONO 0212 5551234 SERVICE 1234567"))

    def test_rif_is_never_a_personal_identity(self):
        text = "DOCUMENTOS DE IDENTIFICACION\nGPS AVILA RIF J-123456789"
        self.assertEqual(extract_identity_number(text), ("rif", "J-123456789"))
        self.assertIsNone(extract_personal_identity(text))

    def test_all_cedulas_dedupes_dotted_and_plain(self):
        self.assertEqual(
            extract_all_cedulas("V-11.222.333 madre C.I. 22.333.444 V-11222333"),
            ["11222333", "22333444"],
        )

    def test_titular_from_ocr_ignores_rif(self):
        name, cedula = extract_titular_from_ocr("TITULAR: JUAN PEREZ\nRIF J-123456789")
        self.assertEqual(name, "Juan Perez")
        self.assertIsNone(cedula)

    def test_titular_from_fact_path_with_name(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/CARTA AVAL FACT 19263 PEDRO ROJAS/FACT 19263 PEDRO ROJAS.pdf"
        )
        self.assertEqual(name, "Pedro Rojas")
        self.assertIsNone(cedula)

    def test_titular_from_glued_fact_number_stem(self):
        name, cedula = extract_titular_from_path(
            "FACTURAS/FACT 7394LUIS PEREZ.pdf"
        )
        self.assertEqual(name, "Luis Perez")
        self.assertIsNone(cedula)

    def test_titular_from_fact_path_with_cedula(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/FACT 7806 ANA TORO 20.333.444.pdf"
        )
        self.assertEqual(name, "Ana Toro")
        self.assertEqual(cedula, "20333444")

    def test_titular_from_folder_when_file_is_egreso(self):
        name, cedula = extract_titular_from_path(
            "FACT 24200 CARMEN SOSA/EGRESO CARMEN SOSA.pdf"
        )
        self.assertEqual(name, "Carmen Sosa")
        self.assertIsNone(cedula)

    def test_titular_ignores_org_folder_and_bare_first_name(self):
        name, cedula = extract_titular_from_path("CORPOELEC/PRESUPUESTO 6737 ANA.pdf")
        self.assertIsNone(name)
        self.assertIsNone(cedula)
        name, cedula = extract_titular_from_path(
            "CORPOELEC/PRESUPUESTO CATARATAS 6817.pdf"
        )
        self.assertIsNone(name)
        self.assertIsNone(cedula)

    def test_titular_strips_campaign_noise_before_person(self):
        name, cedula = extract_titular_from_path(
            "CORPOELEC/PRESUPUESTO CATARATAS RAMON SILVA.pdf"
        )
        self.assertEqual(name, "Ramon Silva")
        self.assertIsNone(cedula)

    def test_titular_strips_leading_invoice_number(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/19263 PEDRO ROJAS/IMG.pdf"
        )
        self.assertEqual(name, "Pedro Rojas")
        self.assertIsNone(cedula)

    def test_batch_folder_facturas_noviembre_is_not_a_person(self):
        name, cedula = extract_titular_from_path(
            "FACTURAS/FACTURAS PREVISORA NOVIEMBRE LOTE 1, 2024/FACT 9351.pdf"
        )
        self.assertIsNone(name)
        self.assertIsNone(cedula)

    def test_fact_stem_still_resolves_titular(self):
        name, cedula = extract_titular_from_path("FACT 19263 PEDRO ROJAS.pdf")
        self.assertEqual(name, "Pedro Rojas")
        self.assertIsNone(cedula)


class OfficePacketTests(unittest.TestCase):
    def test_each_slide_keeps_its_largest_picture(self):
        presentation = """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="1" r:id="rId1"/>
    <p:sldId id="2" r:id="rId2"/>
  </p:sldIdLst>
</p:presentation>
"""
        deck_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
</Relationships>
"""
        slide_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{large}"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{logo}"/>
</Relationships>
"""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            packet = folder / "packet.pptx"
            with zipfile.ZipFile(packet, "w") as archive:
                archive.writestr("ppt/presentation.xml", presentation)
                archive.writestr("ppt/_rels/presentation.xml.rels", deck_rels)
                archive.writestr("ppt/slides/slide1.xml", "<p:sld/>")
                archive.writestr("ppt/slides/slide2.xml", "<p:sld/>")
                archive.writestr(
                    "ppt/slides/_rels/slide1.xml.rels",
                    slide_rels.format(large="image1.jpg", logo="logo.png"),
                )
                archive.writestr(
                    "ppt/slides/_rels/slide2.xml.rels",
                    slide_rels.format(large="image2.jpg", logo="logo.png"),
                )
                archive.writestr("ppt/media/image1.jpg", b"A" * 200)
                archive.writestr("ppt/media/image2.jpg", b"B" * 180)
                archive.writestr("ppt/media/logo.png", b"L" * 10)
            dest = folder / "out"
            dest.mkdir()
            images, error = _render_office(packet, dest)
            self.assertEqual(error, "")
            self.assertEqual(len(images), 2)
            self.assertEqual(images[0].read_bytes(), b"A" * 200)
            self.assertEqual(images[1].read_bytes(), b"B" * 180)


if __name__ == "__main__":
    unittest.main()
