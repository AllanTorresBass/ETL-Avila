"""Held C.1 patients: link an empty slot, replace only a nameless one."""

import unittest

from sin_rol_holds import decide_hold, page_owns_invoice


def decide(**overrides):
    base = dict(
        page_patient_ci="44555666",
        page_titular_ci="11222333",
        patient_ci="44555666",
        patient_name="LUIS DIAZ",
        stored_invoice="200014455",
        ocr_invoice="200014455",
        titular_ci="11222333",
        titular_count=1,
        beneficiaries=[],
        patient_was_cleared=False,
        already_on_invoice=False,
    )
    base.update(overrides)
    return decide_hold(**base)


class HoldDecisionTest(unittest.TestCase):
    def test_empty_slot_links_when_the_page_number_is_the_stored_factura(self):
        found = decide()
        self.assertEqual(found.action, "link")
        self.assertEqual(found.reason, "empty_slot")

    def test_single_number_range_is_the_same_factura(self):
        self.assertTrue(page_owns_invoice("range:20777", "20777"))
        found = decide(stored_invoice="range:20777", ocr_invoice="20777")
        self.assertEqual(found.action, "link")

    def test_a_span_is_not_this_page(self):
        self.assertFalse(page_owns_invoice("range:16751-16864", "16843"))
        found = decide(stored_invoice="range:16751-16864", ocr_invoice="16843")
        self.assertEqual(found.reason, "factura_not_this_page")

    def test_titular_on_the_page_must_be_the_stored_titular(self):
        found = decide(titular_ci="99888777")
        self.assertEqual(found.reason, "titular_mismatch")

    def test_same_cedula_is_not_a_pair(self):
        found = decide(page_titular_ci="44555666", titular_ci="44555666")
        self.assertEqual(found.reason, "page_not_a_pair")

    def test_same_name_without_cedula_is_replaced(self):
        found = decide(beneficiaries=[{"ci": None, "name": "Luis Diaz", "source": "path"}])
        self.assertEqual((found.action, found.reason), ("replace", "same_name_no_ci"))

    def test_a_different_nameless_row_needs_the_clear_in_historial(self):
        junk = [{"ci": None, "name": "Casos Sept", "source": "path"}]
        held = decide(beneficiaries=junk, patient_was_cleared=False)
        self.assertEqual(held.reason, "nameless_other")
        cleared = decide(beneficiaries=junk, patient_was_cleared=True)
        self.assertEqual((cleared.action, cleared.reason), ("replace", "cleared_patient"))

    def test_a_cedula_already_in_the_slot_stays(self):
        found = decide(beneficiaries=[{"ci": "77888999", "name": "ANA RUIZ", "source": "fiscal_ocr"}])
        self.assertEqual(found.reason, "slot_has_ci")

    def test_a_workbook_beneficiario_stays(self):
        found = decide(
            beneficiaries=[{"ci": None, "name": "Luis Diaz", "source": "workbook"}],
        )
        self.assertEqual(found.reason, "workbook_beneficiario")

    def test_two_beneficiarios_stay(self):
        found = decide(
            beneficiaries=[
                {"ci": None, "name": "Luis Diaz", "source": "path"},
                {"ci": None, "name": "Ana Ruiz", "source": "path"},
            ]
        )
        self.assertEqual(found.reason, "many_beneficiarios")

    def test_page_patient_must_be_this_cedula(self):
        found = decide(page_patient_ci="10000001")
        self.assertEqual(found.reason, "page_patient_mismatch")


if __name__ == "__main__":
    unittest.main()
