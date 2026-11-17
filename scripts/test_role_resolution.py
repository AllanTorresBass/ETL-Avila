"""Unit checks for titular/beneficiario resolution helpers (no DB)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from upload_documents_to_blob import (
    _link_path_name_as_beneficiario,
    identity_page_ci,
    promote_ci_person_as_titular,
    titular_promotion_blocker,
    try_promote_ci_titular,
)


def _cursor(fetchone=None, fetchall=None) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall or []
    return cur


class RoleResolutionTests(unittest.TestCase):
    def test_promote_demotes_other_titulars(self):
        cur = MagicMock()
        promote_ci_person_as_titular(cur, "inv-1", "titular-id")
        # First call: demote other titulars
        demote_sql = cur.execute.call_args_list[0][0][0]
        self.assertIn("role = 'beneficiario'", demote_sql)
        self.assertIn("role = 'titular'", demote_sql)

    def test_path_beneficiario_skips_same_person(self):
        cur = _cursor({"full_name": "JUAN JOSE PEREZ GOMEZ", "identity_number": "11222333"})
        result = _link_path_name_as_beneficiario(cur, "inv-1", "Juan Perez", "titular-id")
        self.assertIsNone(result)

    def test_path_beneficiario_skips_identical_id(self):
        cur = _cursor({"full_name": "Other Person", "identity_number": None})
        with patch(
            "upload_documents_to_blob.upsert_by_name",
            return_value=("titular-id", "exists"),
        ):
            result = _link_path_name_as_beneficiario(
                cur, "inv-1", "Someone Else", "titular-id"
            )
        self.assertIsNone(result)

    def test_path_beneficiario_skips_nameless_titular(self):
        # A CI row without a name cannot be compared — the path may be the titular.
        cur = _cursor({"full_name": None, "identity_number": "11222333"})
        with patch("upload_documents_to_blob.upsert_by_name") as upsert:
            result = _link_path_name_as_beneficiario(cur, "inv-1", "Juan Perez", "titular-id")
        self.assertIsNone(result)
        upsert.assert_not_called()

    def test_path_beneficiario_skips_same_path_ci(self):
        cur = _cursor({"full_name": None, "identity_number": "11222333"})
        with patch("upload_documents_to_blob.upsert_by_ci") as upsert:
            result = _link_path_name_as_beneficiario(
                cur, "inv-1", "Juan Perez", "titular-id", path_ci="11222333"
            )
        self.assertIsNone(result)
        upsert.assert_not_called()

    def test_path_beneficiario_with_other_ci_upserts_by_ci(self):
        cur = _cursor({"full_name": "JUAN PEREZ", "identity_number": "11222333"})
        with patch(
            "upload_documents_to_blob.upsert_by_ci", return_value=("child-id", "created")
        ) as upsert, patch("upload_documents_to_blob.link_invoice_person") as link:
            result = _link_path_name_as_beneficiario(
                cur, "inv-1", "Luis Perez", "titular-id", path_ci="20333444"
            )
        self.assertEqual(result, "child-id")
        upsert.assert_called_once()
        link.assert_called_once_with(
            cur, "inv-1", "child-id", "beneficiario", source="path", rule_id="path_beneficiario"
        )


class PromotionGuardTests(unittest.TestCase):
    def test_workbook_titular_with_contact_blocks(self):
        cur = _cursor(
            {"identity_number": "11222333"},
            [{"source": "workbook", "identity_number": None, "phone": "04141234567", "birth_date": None}],
        )
        self.assertEqual(titular_promotion_blocker(cur, "inv-1", "p"), "workbook_titular")

    def test_other_plastic_ci_titular_blocks(self):
        cur = _cursor(
            {"identity_number": "11222333"},
            [{"source": "ocr_cedula", "identity_number": "99888777", "phone": None, "birth_date": None}],
        )
        self.assertEqual(titular_promotion_blocker(cur, "inv-1", "p"), "ci_conflict")

    def test_path_titular_does_not_block(self):
        cur = _cursor(
            {"identity_number": "11222333"},
            [{"source": "path", "identity_number": None, "phone": None, "birth_date": None}],
        )
        self.assertIsNone(titular_promotion_blocker(cur, "inv-1", "p"))

    def test_try_promote_leaves_invoice_alone_when_blocked(self):
        cur = MagicMock()
        with patch(
            "upload_documents_to_blob.titular_promotion_blocker", return_value="workbook_titular"
        ), patch("upload_documents_to_blob.promote_ci_person_as_titular") as promote, patch(
            "upload_documents_to_blob._link_path_name_as_beneficiario"
        ) as link:
            outcome = try_promote_ci_titular(cur, "inv-1", "p", path_name="Luis Perez")
        self.assertEqual(outcome, "workbook_titular")
        promote.assert_not_called()
        link.assert_not_called()

    def test_try_promote_links_path_beneficiario(self):
        cur = MagicMock()
        with patch(
            "upload_documents_to_blob.titular_promotion_blocker", return_value=None
        ), patch("upload_documents_to_blob.promote_ci_person_as_titular") as promote, patch(
            "upload_documents_to_blob._link_path_name_as_beneficiario"
        ) as link:
            outcome = try_promote_ci_titular(cur, "inv-1", "p", path_name="Luis Perez")
        self.assertEqual(outcome, "promoted")
        promote.assert_called_once_with(cur, "inv-1", "p", source="ocr_cedula")
        link.assert_called_once_with(cur, "inv-1", "Luis Perez", "p", None)


class IdentityPageCiTests(unittest.TestCase):
    def test_single_ci(self):
        self.assertEqual(identity_page_ci("CEDULA DE IDENTIDAD V-11.222.333"), ("11222333", "ok"))

    def test_multiple_ci_escalates(self):
        self.assertEqual(
            identity_page_ci("V-11222333 ... C.I. V-22333444"), (None, "multiple")
        )

    def test_multiple_ci_keeps_current_titular(self):
        self.assertEqual(
            identity_page_ci("V-11222333 ... C.I. V-22333444", prefer="22333444"),
            ("22333444", "ok"),
        )

    def test_rif_only_is_none(self):
        self.assertEqual(
            identity_page_ci("DOCUMENTOS DE IDENTIFICACION RIF J-123456789"), (None, "none")
        )


if __name__ == "__main__":
    unittest.main()
