"""Unit tests for role linkage helpers (no Neon)."""

from __future__ import annotations

import unittest
from collections import Counter
from unittest.mock import MagicMock, patch

from fiscal_extract import FiscalFields, link_fiscal_roles
from upload_documents_to_blob import _names_refer_to_same_person


class NameGuardTests(unittest.TestCase):
    def test_short_path_name_is_same_person_as_legal_name(self):
        self.assertTrue(
            _names_refer_to_same_person("JUAN PEREZ", "JUAN CARLOS PEREZ GOMEZ")
        )

    def test_distinct_names_are_not_same(self):
        self.assertFalse(
            _names_refer_to_same_person("PEDRO TORRES", "JUAN PEREZ GOMEZ")
        )


class FiscalPatientLinkTests(unittest.TestCase):
    def test_skips_when_patient_is_titular(self):
        cur = MagicMock()
        stats: Counter = Counter()
        fields = FiscalFields(
            titular_name="JUAN PEREZ",
            titular_ci="11222333",
            patient_name="JUAN PEREZ",
            patient_ci="11222333",
        )
        with patch(
            "person_upsert.upsert_by_ci", return_value=("pid-t", "ok")
        ) as upsert, patch(
            "upload_documents_to_blob.try_promote_ci_titular", return_value="promoted"
        ), patch("upload_documents_to_blob.link_invoice_person") as link:
            link_fiscal_roles(cur, "inv-1", fields, stats)
            link.assert_not_called()
            self.assertEqual(stats["titular:promoted"], 1)
            upsert.assert_called()


if __name__ == "__main__":
    unittest.main()
