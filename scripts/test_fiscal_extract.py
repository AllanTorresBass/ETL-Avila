"""Fiscal sheet field extraction on anonymized OCR layouts."""

from __future__ import annotations

import datetime as dt
import unittest

from fiscal_extract import FiscalFields, extract, invoice_number_agrees, norm_control

FORMA_LIBRE = """G.P.S. GESTION PROFESIONAL DE SALUD AVILA, C.A.
RIF.: J-12345678-9
Nombre y Apellido o Razón Social: N° DE CONTROL 00 012345 » LIBRE
SEGUROS EJEMPLO C.A. Factura N*00012345
CI.,R.LF. O Pasaporte: J123456789 Fecha de Emisión: 05/03/2025
Titular: JUAN PEREZ GOMEZ V-11222333
Paciente: LUIS PEREZ DIAZ C.I:44555666
Tomador: ORDEN:7654321
Facturación Clinica
CONSULTA PEDIATRIA (E) 1 1234567 1/01 1.500,00 0,00 1.500,00
ECOGRAFIA ABDOMINAL (E) 1 1234568 1/01 2.000,00 0,00 2.000,00
TOTAL SERVICIOS COBRABLES 3.500,00
SUB-TOTAL: 3.500,00 0,00
TOTAL FACTURA: 3.500,00 95,50
"""

GLUED_CONTROL = """N?DECONTROL 00— 54321 — »FORMA LIBRE «
Social: SEGUROS EJEMPLO
ORIGINAL BLANCA CLIENTE (Da Derecho A Credito Fiscal)
"""


class FiscalExtractTests(unittest.TestCase):
    def test_full_forma_libre(self):
        f = extract(FORMA_LIBRE)
        self.assertEqual(f.control_number, "00-012345")
        self.assertEqual(norm_control("0-12345"), "00-012345")
        self.assertEqual(f.invoice_number, "12345")
        self.assertEqual(f.issue_date, dt.date(2025, 3, 5))
        self.assertEqual(f.titular_name, "JUAN PEREZ GOMEZ")
        self.assertEqual(f.titular_ci, "11222333")
        self.assertEqual(f.patient_name, "LUIS PEREZ DIAZ")
        self.assertEqual(f.patient_ci, "44555666")
        self.assertEqual(f.clave, "7654321")
        self.assertEqual(f.total_bs, 3500.0)
        self.assertEqual(f.total_usd, 95.5)
        self.assertEqual(f.services, ["CONSULTA PEDIATRIA", "ECOGRAFIA ABDOMINAL"])

    def test_glued_control_number(self):
        self.assertEqual(extract(GLUED_CONTROL).control_number, "00-054321")

    def test_control_number_ocr_variants(self):
        cases = {
            "N* DE CONTROL 00) — 009773» FORMA": "00-009773",
            "N* DE CONTROL (0... 012967 FORMA LIBRE": "00-012967",
            "N* DE CONTROL 00 — 5114 73 FORMA LIBRE": "00-511473",
            "N* DECONTROL  (M— 009746 » FORMA": "00-009746",
        }
        for text, expected in cases.items():
            self.assertEqual(extract(text).control_number, expected, text)

    def test_print_run_range_is_not_control(self):
        self.assertIsNone(extract("IMPRESO 13/03/2025 DESDE EL N* 00-011251 HASTA EL N* 00-011550").control_number)

    def test_preprinted_factura_no(self):
        self.assertEqual(extract("FACTURA NO 0001421 0").invoice_number, "1421")

    def test_rif_on_razon_social_is_not_titular(self):
        f = extract("Razón Social: SEGUROS EJEMPLO\nRIF J-123456789\nFACTURA N 1234")
        self.assertIsNone(f.titular_ci)
        self.assertIsNone(f.patient_ci)

    def test_empty_text(self):
        self.assertEqual(extract(""), FiscalFields())

    def test_merge_fills_gaps_only(self):
        a = FiscalFields(control_number="00-1", services=["A"])
        a.merge(FiscalFields(control_number="00-2", clave="1234", services=["A", "B"]))
        self.assertEqual((a.control_number, a.clave, a.services), ("00-1", "1234", ["A", "B"]))

    def test_invoice_number_agreement(self):
        self.assertTrue(invoice_number_agrees("12345", "12345"))
        self.assertTrue(invoice_number_agrees("12345", "200012345"))
        self.assertTrue(invoice_number_agrees("12345", "21"))
        self.assertTrue(invoice_number_agrees("12345", None))
        self.assertFalse(invoice_number_agrees("12345", "12342"))
        self.assertFalse(invoice_number_agrees("12345", "200012342"))

    def test_implausible_date_dropped(self):
        self.assertIsNone(extract("Fecha de Emisión: 05/03/1899").issue_date)


if __name__ == "__main__":
    unittest.main()
