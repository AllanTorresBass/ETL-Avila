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
    parse_dates,
    address_signature,
    phones_in_text,
    plausible_dob,
    repeated_address_signatures,
    same_address,
    select_address_hits,
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
        self.assertIn("phone", page.letterhead_fields)
        self.assertNotIn("address", page.letterhead_fields)
        self.assertEqual(phones_in_text("RIF J-12345678-9"), [])
        self.assertEqual(canonical_phone("0414-1234567"), "04141234567")

    def test_letterhead_phone_does_not_drop_the_home_address(self):
        text = (
            "CLINICA SANTA FE TELEFONO 0212-5551234\n"
            "DIRECCION CALLE 4 CASA 12 VALERA\n"
        )
        page = extract_page(text, "informe_medico", today=TODAY)
        addresses = [c for c in page.candidates if c.field == "address"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0].rule_id, "form_address")
        self.assertIn("CALLE 4", addresses[0].value)
        self.assertIn("phone", page.letterhead_fields)
        self.assertNotIn("address", page.letterhead_fields)
        person_id, status = bind_candidate(addresses[0], [TITULAR, CHILD])
        self.assertEqual((person_id, status), ("t1", "bound"))

    def test_grouped_patient_phones_and_short_birth_years(self):
        text = (
            "PACIENTE: JUAN PEREZ\n"
            "FECHA DE NACIMIENTO: 18-03-72\n"
            "TELEFONO: 0414-728 37 61\n"
            "CEL: 0412 - 2353151\n"
        )
        page = extract_page(text, "informe_medico", today=TODAY)
        dobs = [c.value for c in page.candidates if c.field == "birth_date"]
        phones = [c.value for c in page.candidates if c.field == "phone"]
        self.assertEqual(dobs, [dt.date(1972, 3, 18)])
        self.assertEqual(phones, ["04147283761", "04122353151"])
        self.assertEqual(phones_in_text("0271-222.41.04"), ["02712224104"])
        self.assertEqual(phones_in_text("+58 412 0876653"), ["04120876653"])
        abbr = extract_page(
            "CEDULA DE IDENTIDAD\nV-11222333\nF. NACIMIENTO 28 SEP. 1976\n",
            "cedula_identidad",
            today=TODAY,
        )
        self.assertEqual(abbr.candidates[0].value, dt.date(1976, 9, 28))
        future = parse_dates("18-12-26", today=TODAY)
        self.assertEqual(future, [])

    def test_clinic_address_dropped(self):
        page = extract_page("DIRECCION CLINICA SANTA FE\n", "comprobante", today=TODAY)
        self.assertEqual([c for c in page.candidates if c.field == "address"], [])
        self.assertIn("address", page.letterhead_fields)
        buried = extract_page("DIRECCION AV BOLIVAR CLINICA SANTA FE\n", "comprobante", today=TODAY)
        self.assertEqual([c for c in buried.candidates if c.field == "address"], [])
        heading = extract_page("DIRECCION DATOS GENERALES DEL PACIENTE\n", "comprobante", today=TODAY)
        self.assertEqual([c for c in heading.candidates if c.field == "address"], [])
        office = extract_page(
            "CALLE 19 CONSULTORIO 110 URB LAS ACACIAS\n",
            "informe_medico",
            today=TODAY,
        )
        self.assertEqual([c for c in office.candidates if c.field == "address"], [])

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
        self.assertTrue(same_address("CALLE 4 CASA 12 VALERA", "CALLE 4 CASA 12"))
        self.assertFalse(same_address("CALLE 4 CASA 12", "CALLE 8 CASA 12"))
        self.assertFalse(same_address("CALLE 4 VALERA", "AVENIDA 4 VALERA"))

    def test_street_line_does_not_block_a_labeled_address(self):
        labeled = Candidate("address", "CALLE 4 CASA 12 VALERA", "form_address", 0.7)
        other = Candidate("address", "AVENIDA BOLIVAR EDIFICIO 3", "street_line", 0.55)
        same = Candidate("address", "CALLE 4 CASA 12", "street_line", 0.55)
        kept = select_address_hits([labeled, other, same])
        self.assertEqual([hit.rule_id for hit in kept], ["form_address", "street_line"])
        self.assertEqual(kept[1].value, "CALLE 4 CASA 12")
        stored = select_address_hits([other], "CALLE 4 CASA 12 VALERA")
        self.assertEqual(stored, [])
        disagree = select_address_hits(
            [
                Candidate("address", "CALLE 4 CASA 12", "street_line", 0.55),
                Candidate("address", "AVENIDA BOLIVAR EDIFICIO 3", "street_line", 0.55),
            ]
        )
        self.assertIsNone(disagree)
        one = select_address_hits([Candidate("address", "CALLE 4 CASA 12 VALERA", "street_line", 0.55)])
        self.assertEqual(len(one), 1)

    def test_repeated_office_address_is_letterhead(self):
        office = "AV BOLIVAR ENTRE CALLES 18 Y 19 SECTOR LAS ACACIAS"
        home = "CALLE 4 CASA 12 VALERA"
        records = [(office, f"inv-{i}", f"p-{i}") for i in range(8)]
        records.append((home, "inv-home", "p-home"))
        denied = repeated_address_signatures(records)
        self.assertIn(address_signature(office), denied)
        self.assertNotIn(address_signature(home), denied)
        self.assertTrue(address_signature(office))

    def test_unbound_form_address_goes_to_the_only_titular(self):
        page = extract_page("INFORME\nDIRECCION CALLE 4 CASA 12 VALERA\n", "informe_medico", today=TODAY)
        address = next(c for c in page.candidates if c.field == "address")
        self.assertIsNone(address.block_ci)
        person_id, status = bind_candidate(address, [TITULAR, CHILD])
        self.assertEqual((person_id, status), ("t1", "bound"))
        other = PersonOnInvoice("t2", "Maria Gil", "99888777", "titular")
        _, ambiguous = bind_candidate(address, [TITULAR, other])
        self.assertEqual(ambiguous, "ambiguous")
        _, blocked = bind_candidate(address, [TITULAR], blocked=True)
        self.assertEqual(blocked, "blocked_review")
        owned = Candidate("address", "CALLE 9 CASA 1", "form_address", 0.7, block_ci="99888777")
        owner_id, owner_status = bind_candidate(
            owned, [TITULAR, other], persons_by_ci={"99888777": "t2"}
        )
        self.assertEqual((owner_id, owner_status), ("t2", "bound"))
        unnamed = Candidate("address", "CALLE 4 CASA 12 VALERA", "form_address", 0.7, block_name="PEDRO LOPEZ")
        fallback_id, fallback_status = bind_candidate(unnamed, [TITULAR, CHILD])
        self.assertEqual((fallback_id, fallback_status), ("t1", "bound"))
        twin = PersonOnInvoice("t2", "Juan Perez Gonzalez", "99888777", "titular")
        shared = Candidate("address", "CALLE 4 CASA 12 VALERA", "form_address", 0.7, block_name="JUAN PEREZ")
        _, two_names = bind_candidate(shared, [TITULAR, twin])
        self.assertEqual(two_names, "ambiguous")

    def test_street_line_without_the_word_direccion(self):
        page = extract_page("INFORME MEDICO\nCALLE 4 CASA 12 VALERA\n", "informe_medico", today=TODAY)
        addresses = [c for c in page.candidates if c.field == "address"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0].rule_id, "street_line")
        self.assertIn("CALLE 4", addresses[0].value)
        prose = extract_page("EL SECTOR AFECTADO ES LA CORNEA 2\n", "informe_medico", today=TODAY)
        self.assertEqual([c for c in prose.candidates if c.field == "address"], [])
        lab = extract_page("CALLE 4 CASA 12 VALERA\n", "laboratorio", today=TODAY)
        self.assertEqual(lab.candidates, [])
        office = extract_page(
            "AV BOLIVAR ENTRE CALLES 18 Y 19 NIVEL 1 LOCAL 10\n",
            "informe_medico",
            today=TODAY,
        )
        self.assertEqual([c for c in office.candidates if c.field == "address"], [])
        footer = extract_page(
            "URB. LAS FLORES, VALERA, TRUJILLO, VENEZUELA. TELEFONO: 0271-2310571\n",
            "informe_medico",
            today=TODAY,
        )
        self.assertEqual([c for c in footer.candidates if c.field == "address"], [])


if __name__ == "__main__":
    unittest.main()
