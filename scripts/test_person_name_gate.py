"""Unit checks for person name gate (no DB)."""

from __future__ import annotations

import unittest

from person_name_gate import (
    is_date_like_identity,
    is_usable_person_name,
    sanitize_person_name,
)


class PersonNameGateTests(unittest.TestCase):
    def test_rejects_venezolana_variants(self):
        for raw in (
            "Venezolana",
            "Venezolano",
            "Venezolana.",
            "Venezolano!",
            "Venezolanas",
            "Venezolanoe",
        ):
            self.assertFalse(is_usable_person_name(raw), raw)
            self.assertIsNone(sanitize_person_name(raw))

    def test_rejects_form_labels(self):
        self.assertFalse(is_usable_person_name("Idos Y Nombre"))
        self.assertFalse(is_usable_person_name("Nombres As"))
        self.assertFalse(is_usable_person_name("Apellidos"))
        # Label crumbs strip away; a real two-token name can remain.
        self.assertEqual(
            sanitize_person_name("Jean Carlos Apellidos Cedula Identidad"),
            "Jean Carlos",
        )

    def test_rejects_date_as_name(self):
        self.assertFalse(is_usable_person_name("20260514 (127)"))
        self.assertTrue(is_date_like_identity("20260514"))
        self.assertFalse(is_date_like_identity("11222333"))

    def test_rejects_single_token(self):
        self.assertFalse(is_usable_person_name("De"))
        self.assertFalse(is_usable_person_name("Ls"))

    def test_accepts_real_names(self):
        self.assertTrue(is_usable_person_name("Juan Perez"))
        self.assertTrue(is_usable_person_name("Maria De Los Angeles Lopez"))
        self.assertEqual(sanitize_person_name("  Juan  Perez "), "Juan Perez")

    def test_cedula_ocr_does_not_return_nationality(self):
        from document_types import extract_name_from_cedula_ocr

        text = (
            "CEDULA DE IDENTIDAD\n"
            "APELLIDOS: VENEZOLANA\n"
            "NOMBRES: VENEZOLANO\n"
            "V-11.222.333"
        )
        self.assertIsNone(extract_name_from_cedula_ocr(text))

    def test_cedula_ocr_keeps_real_card_name(self):
        from document_types import extract_name_from_cedula_ocr

        text = (
            "CEDULA DE IDENTIDAD\n"
            "APELLIDOS: PEREZ GOMEZ\n"
            "NOMBRES: JUAN JOSE\n"
            "NACIONALIDAD VENEZOLANA\n"
            "V-11.222.333"
        )
        name = extract_name_from_cedula_ocr(text)
        self.assertIsNotNone(name)
        self.assertIn("Juan", name or "")
        self.assertIn("Perez", name or "")
        self.assertNotIn("Venezolan", name or "")


if __name__ == "__main__":
    unittest.main()
