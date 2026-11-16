"""Unit checks for titular/beneficiario resolution helpers (no DB)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from upload_documents_to_blob import (
    _link_path_name_as_beneficiario,
    promote_ci_person_as_titular,
)


class RoleResolutionTests(unittest.TestCase):
    def test_promote_demotes_other_titulars(self):
        cur = MagicMock()
        promote_ci_person_as_titular(cur, "inv-1", "helber-id")
        # First call: demote other titulars
        demote_sql = cur.execute.call_args_list[0][0][0]
        self.assertIn("role = 'beneficiario'", demote_sql)
        self.assertIn("role = 'titular'", demote_sql)

    def test_path_beneficiario_skips_same_person(self):
        cur = MagicMock()
        with patch(
            "upload_documents_to_blob.upsert_by_name",
            return_value=("helber-id", "exists"),
        ):
            result = _link_path_name_as_beneficiario(
                cur, "inv-1", "Helber Jose", "helber-id"
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
