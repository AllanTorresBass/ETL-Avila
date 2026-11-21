"""Invoice-truth decisions on fake packets. No database and no real patients."""

from __future__ import annotations

import unittest

from invoice_truth_decide import decide_record


def _card(name: str, ci: str, document_id: str = "doc-1") -> dict:
    return {
        "document_id": document_id,
        "page_index": 2,
        "document_type": "cedula_identidad",
        "backup_path": "FACT 100.pdf",
        "name": name,
        "cedulas": [ci],
    }


def _row(**overrides) -> dict:
    base = {
        "invoice_id": "inv-1",
        "invoice_number": "100",
        "fiscal_titular_name": None,
        "fiscal_titular_ci": None,
        "fiscal_patient_name": None,
        "fiscal_patient_ci": None,
        "fiscal_backup_path": None,
        "fiscal_page_index": None,
        "cards": [],
        "acta_parent_cis": [],
        "path_name": None,
        "path_ci": None,
    }
    base.update(overrides)
    return base


class InvoiceTruthDecideTests(unittest.TestCase):
    def test_matching_patient_is_self(self):
        decision = decide_record(
            _row(
                fiscal_titular_name="JUAN PEREZ",
                fiscal_titular_ci="11222333",
                fiscal_patient_name="JUAN PEREZ",
                fiscal_patient_ci="11222333",
                cards=[_card("JUAN PEREZ", "11222333")],
            )
        )
        self.assertEqual(decision["outcome"], "self")
        self.assertEqual(decision["titular_ci"], "11222333")
        self.assertEqual(decision["titular_source"], "fiscal_ocr")
        self.assertIsNone(decision["beneficiario_name"])

    def test_different_patient_is_pair(self):
        decision = decide_record(
            _row(
                fiscal_titular_name="JUAN PEREZ",
                fiscal_titular_ci="11222333",
                fiscal_patient_name="LUIS PEREZ DIAZ",
                fiscal_patient_ci="44555666",
                cards=[_card("JUAN PEREZ", "11222333")],
            )
        )
        self.assertEqual(decision["outcome"], "pair")
        self.assertEqual(decision["titular_ci"], "11222333")
        self.assertEqual(decision["beneficiario_name"], "LUIS PEREZ DIAZ")
        self.assertEqual(decision["beneficiario_ci"], "44555666")
        self.assertEqual(decision["beneficiario_source"], "fiscal_ocr")

    def test_two_unplaced_cards_are_review(self):
        decision = decide_record(
            _row(
                cards=[
                    _card("JUAN PEREZ", "11222333", "doc-1"),
                    _card("LUIS PEREZ", "44555666", "doc-2"),
                ]
            )
        )
        self.assertEqual(decision["outcome"], "review")
        self.assertEqual(decision["reason"], "unassigned_cards")

    def test_acta_parent_only_is_review(self):
        decision = decide_record(_row(acta_parent_cis=["11222333"]))
        self.assertEqual(decision["outcome"], "review")
        self.assertEqual(decision["reason"], "acta_only")

    def test_folder_name_becomes_beneficiario(self):
        decision = decide_record(
            _row(
                cards=[_card("JUAN PEREZ", "11222333")],
                path_name="LUIS PEREZ DIAZ",
                path_ci="99888777",
            )
        )
        self.assertEqual(decision["outcome"], "pair")
        self.assertEqual(decision["beneficiario_source"], "path")
        self.assertEqual(decision["beneficiario_name"], "LUIS PEREZ DIAZ")
        self.assertEqual(decision["titular_ci"], "11222333")
        self.assertIsNone(decision["beneficiario_ci"])

    def test_folder_cedula_loses_to_the_card(self):
        decision = decide_record(
            _row(
                cards=[_card("JUAN PEREZ", "11222333")],
                path_name="JUAN PEREZ",
                path_ci="99888777",
            )
        )
        self.assertEqual(decision["outcome"], "self")
        self.assertEqual(decision["titular_ci"], "11222333")
        self.assertNotEqual(decision["titular_ci"], "99888777")

    def test_fiscal_ci_missing_from_cards_is_review(self):
        decision = decide_record(
            _row(
                fiscal_titular_name="JUAN PEREZ",
                fiscal_titular_ci="11222333",
                cards=[_card("LUIS PEREZ", "44555666")],
            )
        )
        self.assertEqual(decision["outcome"], "review")
        self.assertEqual(decision["reason"], "fiscal_card_mismatch")

    def test_no_cedula_is_review(self):
        decision = decide_record(_row())
        self.assertEqual(decision["outcome"], "review")
        self.assertEqual(decision["reason"], "no_titular_ci")

    def test_unnamed_card_is_review(self):
        decision = decide_record(
            _row(cards=[_card("CEDULA IDENTIDAD", "11222333")])
        )
        self.assertEqual(decision["outcome"], "review")
        self.assertEqual(decision["reason"], "unnamed_card")


if __name__ == "__main__":
    unittest.main()
