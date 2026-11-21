"""Unit checks for role verification cohorts (no DB)."""

from __future__ import annotations

import unittest

from role_cohorts import (
    ACTIONS,
    COHORTS,
    MISMATCH_FISCAL_ACTION,
    assign_cohort,
    patient_differs_from_titular,
)


class PatientDiffersTests(unittest.TestCase):
    def test_same_name_subset_is_not_different(self):
        self.assertFalse(
            patient_differs_from_titular(
                titular_name="JUAN JOSE PEREZ GOMEZ",
                titular_ci="11222333",
                patient_name="Juan Perez",
                patient_ci=None,
            )
        )

    def test_different_path_name(self):
        self.assertTrue(
            patient_differs_from_titular(
                titular_name="JUAN PEREZ",
                titular_ci="11222333",
                patient_name="Luis Perez",
                patient_ci=None,
            )
        )

    def test_different_path_ci(self):
        self.assertTrue(
            patient_differs_from_titular(
                titular_name="JUAN PEREZ",
                titular_ci="11222333",
                patient_name="Luis Perez",
                patient_ci="20333444",
            )
        )

    def test_same_ci_not_different(self):
        self.assertFalse(
            patient_differs_from_titular(
                titular_name=None,
                titular_ci="11222333",
                patient_name="Juan Perez",
                patient_ci="11222333",
            )
        )

    def test_nameless_titular_with_path_name_not_mismatch(self):
        # Same-person risk — cohort should be nameless_titular, not mismatch.
        self.assertFalse(
            patient_differs_from_titular(
                titular_name=None,
                titular_ci="11222333",
                patient_name="Juan Perez",
                patient_ci=None,
            )
        )


class AssignCohortTests(unittest.TestCase):
    def test_cohort_priority_multi_titular(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 2,
                "beneficiario_count": 0,
                "open_reviews": ["ci_conflict"],
            }
        )
        self.assertEqual(cohort, "multi_titular")
        self.assertEqual(action, ACTIONS["multi_titular"])

    def test_blocked_review(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "11222333",
                "open_reviews": ["workbook_titular"],
            }
        )
        self.assertEqual(cohort, "blocked_review")
        self.assertEqual(action, "open_or_resolve_review")

    def test_no_titular(self):
        cohort, _ = assign_cohort({"titular_count": 0, "beneficiario_count": 0})
        self.assertEqual(cohort, "no_titular")

    def test_id_docs_no_ci(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "",
                "has_id_docs": True,
            }
        )
        self.assertEqual(cohort, "id_docs_no_ci")
        self.assertEqual(action, "strengthen_ci_ocr")

    def test_mismatch_path(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "11222333",
                "path_name": "Luis Perez",
                "has_id_docs": False,
            }
        )
        self.assertEqual(cohort, "mismatch_no_beneficiario")
        self.assertEqual(action, "link_path_beneficiario")

    def test_mismatch_fiscal_prefers_fiscal_action(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "11222333",
                "fiscal_patient_name": "Luis Perez",
                "fiscal_patient_ci": "20333444",
            }
        )
        self.assertEqual(cohort, "mismatch_no_beneficiario")
        self.assertEqual(action, MISMATCH_FISCAL_ACTION)

    def test_self_visit_when_path_is_short_form(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN JOSE PEREZ GOMEZ",
                "titular_ci": "11222333",
                "path_name": "Juan Perez",
                "titular_source": "ocr_cedula",
                "has_id_docs": True,
            }
        )
        self.assertEqual(cohort, "self_visit_ok")
        self.assertEqual(action, "noop_self_visit")

    def test_nameless_titular(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "",
                "titular_ci": "11222333",
                "path_name": "Juan Perez",
                "has_id_docs": False,
            }
        )
        self.assertEqual(cohort, "nameless_titular")
        self.assertEqual(action, "fill_titular_name")

    def test_resolved_pair(self):
        cohort, _ = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 1,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "11222333",
            }
        )
        self.assertEqual(cohort, "resolved_pair")

    def test_weak_evidence(self):
        cohort, action = assign_cohort(
            {
                "titular_count": 1,
                "beneficiario_count": 0,
                "titular_name": "JUAN PEREZ",
                "titular_ci": "",
                "titular_source": "legacy_unknown",
                "has_id_docs": False,
            }
        )
        self.assertEqual(cohort, "weak_evidence")
        self.assertEqual(action, "reclassify_identity")

    def test_every_cohort_has_action(self):
        for cohort in COHORTS:
            self.assertIn(cohort, ACTIONS)


class CollageCiExtractionTests(unittest.TestCase):
    def test_dotted_cedula_without_prefix(self):
        from document_types import extract_all_cedulas

        found = extract_all_cedulas(
            "DOCUMENTOS DE IDENTIFICACION\nAPELLIDOS PEREZ\nNOMBRES JUAN\n11.222.333"
        )
        self.assertIn("11222333", found)

    def test_bare_cedula_near_cue(self):
        from document_types import extract_all_cedulas

        found = extract_all_cedulas("CEDULA DE IDENTIDAD\nNACIONALIDAD VENEZOLANA\n11222333")
        self.assertIn("11222333", found)

    def test_name_from_collage_card_fields(self):
        from document_types import extract_name_from_cedula_ocr

        name = extract_name_from_cedula_ocr(
            "DOCUMENTOS DE IDENTIFICACION\n"
            "CEDULA DE IDENTIDAD\n"
            "APELLIDOS: PEREZ GOMEZ\n"
            "NOMBRES: JUAN JOSE\n"
            "V-11.222.333"
        )
        self.assertIsNotNone(name)
        self.assertIn("Juan", name or "")
        self.assertIn("Perez", name or "")


if __name__ == "__main__":
    unittest.main()
