"""Unit tests for workbook header mapping and CI normalization."""

from __future__ import annotations

import datetime as dt
import unittest

import repair_workbook_birth_dates as repair
import repair_workbook_contact as contact_repair
from document_types import extract_identity_number, extract_name_from_cedula_ocr
from workbook_enrichment.normalize import (
    digits_ci,
    map_headers,
    parse_invoice_number,
    row_dict,
)
from workbook_enrichment.upsert_persons import (
    contact_assignments,
    row_is_titular_self,
    titular_birth_date,
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

    def test_sabana_single_birth_column_is_beneficiary(self):
        headers = ["TITULAR", "CI TITULAR", "BENEFICIARIO", "CI BENEFICIARIO", "FECHA DE NACIMIENTO", "PARENTESCO"]
        mapping = map_headers(headers)
        self.assertEqual(mapping[4], "beneficiario_birth_date")
        row = row_dict(headers, ["ANA PEREZ", "11222333", "LUIS PEREZ", "44555666", "02/03/2015", "HIJO"])
        self.assertIsNone(row["birth_date"])
        self.assertEqual(row["beneficiario_birth_date"], dt.date(2015, 3, 2))

    def test_relacion_two_birth_columns_split_by_position(self):
        headers = [
            "TITULAR",
            "CEDULA DE IDENTIDAD",
            "FECHA DE NACIMIENTO",
            "BENEFICIARIO",
            "CEDULA DE IDENTIDAD",
            "FECHA DE NACIMIENTO",
        ]
        mapping = map_headers(headers)
        self.assertEqual(mapping[2], "birth_date")
        self.assertEqual(mapping[5], "beneficiario_birth_date")

    def test_emergency_phone_is_not_the_household_phone(self):
        headers = [
            "TITULAR",
            "CI TITULAR",
            "BENEFICIARIO",
            "CI BENEFICIARIO",
            "TELEFONO",
            "TELEFONO CONTACTO BENEFICIARIO (EMERGENCIAS)",
            "DIRECCION",
        ]
        mapping = map_headers(headers)
        self.assertEqual(mapping[4], "phone")
        self.assertEqual(mapping[5], "beneficiario_phone")
        self.assertEqual(mapping[6], "address")
        row = row_dict(
            headers,
            ["ANA PEREZ", "11222333", "LUIS PEREZ", "44555666", "0414-1234567", "0412-7654321", "Calle 4 Casa 12"],
        )
        assigned = {(key[1], field): value for key, field, value in contact_assignments(row)}
        self.assertEqual(assigned[("11222333", "phone")], "04141234567")
        self.assertEqual(assigned[("11222333", "address")], "Calle 4 Casa 12")
        self.assertEqual(assigned[("44555666", "phone")], "04127654321")
        self.assertIn(("44555666", "phone_clear_if"), {(key[1], field) for key, field, _ in contact_assignments(row)})

    def test_parse_invoice_number(self):
        self.assertEqual(parse_invoice_number("FACT 22314"), "22314")
        self.assertEqual(parse_invoice_number(22314), "22314")
        self.assertEqual(parse_invoice_number("004277"), "4277")


D1 = dt.date(1980, 1, 1)
D2 = dt.date(2015, 3, 2)


class BirthDateOwnershipTests(unittest.TestCase):
    def _row(self, **kw):
        base = {
            "titular_name": "ANA PEREZ",
            "titular_ci": "11222333",
            "beneficiario_name": "LUIS PEREZ",
            "beneficiario_ci": "44555666",
            "birth_date": None,
            "beneficiario_birth_date": D2,
            "parentesco": "HIJO",
        }
        base.update(kw)
        return base

    def test_child_row_gives_titular_no_dob(self):
        row = self._row()
        self.assertFalse(row_is_titular_self(row))
        self.assertIsNone(titular_birth_date(row, same_person=False))

    def test_self_row_by_ci_gives_titular_the_dob(self):
        row = self._row(beneficiario_name="ANA PEREZ", beneficiario_ci="11222333", beneficiario_birth_date=D1)
        self.assertTrue(row_is_titular_self(row))
        self.assertEqual(titular_birth_date(row, same_person=True), D1)

    def test_parentesco_titular_without_other_person(self):
        row = self._row(beneficiario_name=None, beneficiario_ci=None, parentesco="Titular", beneficiario_birth_date=D1)
        self.assertTrue(row_is_titular_self(row))

    def test_different_ci_wins_over_parentesco_label(self):
        self.assertFalse(row_is_titular_self(self._row(parentesco="TITULAR")))

    def test_attributions_flag_legacy_titular_date(self):
        corrected, legacy = repair.attributions(self._row())
        self.assertEqual(corrected, [(("ci", "44555666"), D2)])
        self.assertIn((("ci", "11222333"), D2), legacy)

    def test_contact_fill_does_not_overwrite(self):
        self.assertEqual(contact_repair._decide("phone", None, {"0414-1234567"})[0], "fill")
        self.assertEqual(contact_repair._decide("phone", "04141234567", {"0414-1234567"})[0], "keep")
        self.assertEqual(contact_repair._decide("phone", "04129998877", {"04141234567"})[0], "conflict")
        action, value = contact_repair._decide("phone", None, {"04141234567", "02125551234"})
        self.assertEqual(action, "fill")
        self.assertEqual(value, "04141234567")

    def test_decide(self):
        self.assertEqual(repair.decide(D2, set(), {D2}), ("clear", None))
        self.assertEqual(repair.decide(D2, {D1}, {D2}), ("set", D1))
        self.assertEqual(repair.decide(D1, {D1}, {D2}), ("keep", None))
        self.assertEqual(repair.decide(D2, {D1, dt.date(1981, 1, 1)}, {D2}), ("conflict", None))
        self.assertEqual(repair.decide(dt.date(1990, 5, 5), set(), {D2}), ("keep", None))


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
