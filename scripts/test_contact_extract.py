"""Contact parsers. Fixtures are fake (JUAN PEREZ, 11222333)."""

from __future__ import annotations

import datetime as dt
import unittest

from contact_extract import (
    Candidate,
    PersonOnInvoice,
    bind_candidate,
    canonical_phone,
    extract_page,
    is_minor_beneficiario,
    names_compatible,
    phones_in_text,
    plausible_dob,
    same_address,
)

TODAY = dt.date(2026, 11, 17)
TITULAR = PersonOnInvoice("t1", "Juan Perez", "11222333", "titular")
CHILD = PersonOnInvoice("c1", "Luis Perez", None, "beneficiario", "hijo")


class ParseTests(unittest.TestCase):
    def test_cedula_dob_keeps_the_card_ci(self):
        text = "CEDULA DE IDENTIDAD\nV-11222333\nF. NACIMIENTO 15/03/1980\n"
        page = extract_page(text, "cedula_identidad", today=TODAY)
        self.assertEqual(len(page.candidates), 1)
        dob = page.candidates[0]
        self.assertEqual(dob.field, "birth_date")
        self.assertEqual(dob.value, dt.date(1980, 3, 15))
        self.assertEqual(dob.rule_id, "cedula_dob")
        self.assertEqual(dob.block_ci, "11222333")

    def test_spanish_month_and_blank_excel_date(self):
        text = "CEDULA DE IDENTIDAD\nV-11222333\nFECHA DE NACIMIENTO 15 DE MARZO DE 1980\n"
        page = extract_page(text, "cedula_identidad", today=TODAY)
        self.assertEqual(page.candidates[0].value, dt.date(1980, 3, 15))
        blank = extract_page("V-11222333\nF. NACIMIENTO 01/01/1899\n", "cedula_identidad", today=TODAY)
        self.assertEqual(blank.candidates, [])
        self.assertIn("birth_date", blank.cues)
        self.assertFalse(plausible_dob(dt.date(1899, 1, 1), today=TODAY))

    def test_collage_dates_stay_with_their_card(self):
        text = (
            "CEDULA DE IDENTIDAD\nV-11222333\nF. NACIMIENTO 15/03/1980\n"
            "CEDULA DE IDENTIDAD\nV-44555666\nF. NACIMIENTO 02/03/2015\n"
        )
        page = extract_page(text, "documentos_identificacion", today=TODAY)
        pairs = {(c.block_ci, c.value) for c in page.candidates}
        self.assertEqual(pairs, {("11222333", dt.date(1980, 3, 15)), ("44555666", dt.date(2015, 3, 2))})

    def test_acta_child_date_and_presentante_address(self):
        text = (
            "ACTA DE NACIMIENTO\n"
            "EL NACIDO FECHA DE NACIMIENTO 02/03/2015\n"
            "PADRE V-11222333 FECHA DE NACIMIENTO 01/01/1980\n"
            "PRESENTANTE DOMICILIO CALLE 4 CASA 12 VALERA\n"
        )
        page = extract_page(text, "acta_nacimiento", today=TODAY)
        dobs = [c for c in page.candidates if c.field == "birth_date"]
        addresses = [c for c in page.candidates if c.field == "address"]
        self.assertEqual(len(dobs), 1)
        self.assertEqual(dobs[0].value, dt.date(2015, 3, 2))
        self.assertEqual(dobs[0].rule_id, "acta_child_dob")
        self.assertIsNone(dobs[0].block_ci)
        self.assertEqual(addresses[0].rule_id, "acta_domicilio")
        self.assertIn("CALLE 4", addresses[0].value)

    def test_informe_phone_next_to_patient_name(self):
        text = "PACIENTE: JUAN PEREZ\nTELEFONO 0414-1234567\n"
        page = extract_page(text, "informe_medico", today=TODAY)
        phones = [c for c in page.candidates if c.field == "phone"]
        self.assertEqual(len(phones), 1)
        self.assertEqual(phones[0].value, "04141234567")
        self.assertEqual(phones[0].rule_id, "informe_phone")
        self.assertIn("JUAN", phones[0].block_name or "")

    def test_clinic_letterhead_and_rif_are_not_phones(self):
        page = extract_page("CLINICA SANTA FE TELEFONO 0212-5551234\n", "informe_medico", today=TODAY)
        self.assertEqual([c for c in page.candidates if c.field == "phone"], [])
        self.assertTrue(page.rejected_letterhead)
        self.assertEqual(phones_in_text("RIF J-12345678-9"), [])
        self.assertEqual(canonical_phone("0414-1234567"), "04141234567")

    def test_clinic_address_dropped(self):
        page = extract_page("DIRECCION CLINICA SANTA FE\n", "comprobante", today=TODAY)
        self.assertEqual([c for c in page.candidates if c.field == "address"], [])

    def test_mobile_and_landline_in_one_patient_block(self):
        text = "ASEGURADO: JUAN PEREZ TELEFONO 0414-1234567 / 0212-5551234\n"
        page = extract_page(text, "comprobante", today=TODAY)
        numbers = [c.value for c in page.candidates if c.field == "phone"]
        self.assertEqual(numbers, ["04141234567", "02125551234"])
        conf = {c.value: c.confidence for c in page.candidates if c.field == "phone"}
        self.assertGreater(conf["04141234567"], conf["02125551234"])


class BindTests(unittest.TestCase):
    def test_ci_binds_even_when_the_invoice_is_blocked(self):
        candidate = Candidate("birth_date", dt.date(1980, 3, 15), "cedula_dob", 0.9, block_ci="11222333")
        person_id, status = bind_candidate(
            candidate, [TITULAR, CHILD], blocked=True, persons_by_ci={"11222333": "t1"}
        )
        self.assertEqual((person_id, status), ("t1", "bound"))

    def test_name_must_match_one_person(self):
        candidate = Candidate("phone", "04141234567", "informe_phone", 0.8, block_name="JUAN PEREZ")
        person_id, status = bind_candidate(candidate, [TITULAR, CHILD])
        self.assertEqual((person_id, status), ("t1", "bound"))
        other = PersonOnInvoice("t2", "Juan Perez Gonzalez", "99888777", "titular")
        _, ambiguous = bind_candidate(candidate, [TITULAR, other])
        self.assertEqual(ambiguous, "ambiguous")

    def test_blocked_name_is_not_used(self):
        candidate = Candidate("phone", "04141234567", "informe_phone", 0.8, block_name="JUAN PEREZ")
        person_id, status = bind_candidate(candidate, [TITULAR], blocked=True)
        self.assertEqual((person_id, status), (None, "blocked_review"))

    def test_acta_defaults(self):
        dob = Candidate("birth_date", dt.date(2015, 3, 2), "acta_child_dob", 0.85)
        address = Candidate("address", "CALLE 4 CASA 12 VALERA", "acta_domicilio", 0.75)
        child_id, child_status = bind_candidate(dob, [TITULAR, CHILD])
        titular_id, titular_status = bind_candidate(address, [TITULAR, CHILD])
        self.assertEqual((child_id, child_status), ("c1", "bound"))
        self.assertEqual((titular_id, titular_status), ("t1", "bound"))

    def test_two_children_do_not_take_the_acta_date(self):
        sibling = PersonOnInvoice("c2", "Ana Perez", None, "beneficiario", "hija")
        dob = Candidate("birth_date", dt.date(2015, 3, 2), "acta_child_dob", 0.85)
        _, status = bind_candidate(dob, [TITULAR, CHILD, sibling])
        self.assertEqual(status, "ambiguous")

    def test_names_and_minor(self):
        self.assertTrue(names_compatible("JUAN PEREZ", "Juan Perez Gonzalez"))
        self.assertFalse(names_compatible("PEREZ", "Juan Perez"))
        self.assertTrue(is_minor_beneficiario("beneficiario", "hijo"))
        self.assertFalse(is_minor_beneficiario("titular", "hijo"))
        self.assertTrue(is_minor_beneficiario("beneficiario", None, dt.date(2015, 3, 2), today=TODAY))
        self.assertFalse(is_minor_beneficiario("beneficiario", None, dt.date(1980, 3, 15), today=TODAY))
        self.assertTrue(same_address("Calle 4 Casa 12 Valera", "CALLE 4 CASA 12 VALERA"))


if __name__ == "__main__":
    unittest.main()
