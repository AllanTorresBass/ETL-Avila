"""Unit tests for workbook header mapping and CI normalization."""

from __future__ import annotations

import unittest

from document_types import extract_identity_number, extract_name_from_cedula_ocr
from workbook_enrichment.normalize import (
    digits_ci,
    map_headers,
    parse_invoice_number,
    row_dict,
)


class NormalizeTests(unittest.TestCase):
    def test_digits_ci_dotted(self):
        self.assertEqual(digits_ci("V-12.345.678"), "12345678")
        self.assertEqual(digits_ci(12345678), "12345678")

    def test_map_duplicate_cedula_columns(self):
        headers = [
            "TITULAR",
            "CEDULA DE IDENTIDAD",
            "BENEFICIARIO",
            "CEDULA DE IDENTIDAD",
            "TELEFONO",
        ]
        mapping = map_headers(headers)
        self.assertEqual(mapping[1], "titular_ci")
        self.assertEqual(mapping[3], "beneficiario_ci")
        self.assertEqual(mapping[4], "phone")

    def test_row_dict_sabana_like(self):
        headers = [
            "CLAVE RMS",
            "TITULAR",
            "CI TITULAR",
            "BENEFICIARIO",
            "CI BENEFICIARIO",
            "PARENTESCO",
            "DIAGNOSTICO",
        ]
        values = ["RMS-1", "ANA PEREZ", "12.345.678", "LUIS PEREZ", "98.765.432", "H", "GRIPE"]
        row = row_dict(headers, values)
        self.assertEqual(row["titular_ci"], "12345678")
        self.assertEqual(row["beneficiario_ci"], "98765432")
        self.assertEqual(row["parentesco"], "H")
        self.assertEqual(row["clave_rms"], "RMS-1")

    def test_parse_invoice_number(self):
        self.assertEqual(parse_invoice_number("FACT 22314"), "22314")
        self.assertEqual(parse_invoice_number(22314), "22314")
        self.assertEqual(parse_invoice_number("004277"), "4277")


class CedulaOcrTests(unittest.TestCase):
    def test_extract_identity(self):
        text = "CEDULA DE IDENTIDAD\nV-12345678\nREPUBLICA BOLIVARIANA"
        self.assertEqual(extract_identity_number(text), ("cedula", "12345678"))

    def test_extract_name_from_card(self):
        text = (
            "REPUBLICA BOLIVARIANA DE VENEZUELA\n"
            "CEDULA DE IDENTIDAD\n"
            "APELLIDOS PEREZ GONZALEZ\n"
            "NOMBRES MARIA JOSE\n"
            "V-12345678"
        )
        name = extract_name_from_cedula_ocr(text)
        self.assertIsNotNone(name)
        self.assertIn("Maria", name or "")
        self.assertIn("Perez", name or "")


if __name__ == "__main__":
    unittest.main()
