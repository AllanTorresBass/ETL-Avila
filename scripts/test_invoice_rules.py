"""Path-string tests for invoice classification. No backup files are opened."""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import (
    classify_document,
    extract_identity_number,
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
        dtype, evidence = classify_document("REPUBLICA BOLIVARIANA DE VENEZUELA\nCEDULA DE IDENTIDAD\nV-12.345.678")
        self.assertEqual(dtype, "cedula_identidad")
        self.assertEqual(evidence, "cedula_card")

    def test_egreso_from_path(self):
        dtype, _ = classify_document("texto clinico", backup_path="FACTURAS/EGRESO EJEMPLO FACT 1000.pdf")
        self.assertEqual(dtype, "egreso")

    def test_comprobante_maps(self):
        dtype, _ = classify_document("COMPROBANTE DE AUTORIZACION\nRIF J-302020476")
        self.assertEqual(dtype, "comprobante")

    def test_extract_cedula_digits(self):
        found = extract_identity_number("CEDULA DE IDENTIDAD\nV-12345678\nNOMBRE")
        self.assertEqual(found, ("cedula", "12345678"))

    def test_titular_from_fact_path_with_name(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/CARTA AVAL FACT 19263 NELSON VALERA/FACT 19263 NELSON VALERA.pdf"
        )
        self.assertEqual(name, "Nelson Valera")
        self.assertIsNone(cedula)

    def test_titular_from_fact_path_with_cedula(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/FACT 7806 AMALI LAREZ 30.107.906.pdf"
        )
        self.assertEqual(name, "Amali Larez")
        self.assertEqual(cedula, "30107906")

    def test_titular_from_folder_when_file_is_egreso(self):
        name, cedula = extract_titular_from_path(
            "FACT 24200 MARIA RUZZA/EGRESO MARIA RUZZA.pdf"
        )
        self.assertEqual(name, "Maria Ruzza")
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
            "CORPOELEC/PRESUPUESTO CATARATAS ESTANISLAO BARRIOS.pdf"
        )
        self.assertEqual(name, "Estanislao Barrios")
        self.assertIsNone(cedula)

    def test_titular_strips_leading_invoice_number(self):
        name, cedula = extract_titular_from_path(
            "SCANER SEGURO MIRANDA/19263 NELSON VALERA/IMG.pdf"
        )
        self.assertEqual(name, "Nelson Valera")
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
