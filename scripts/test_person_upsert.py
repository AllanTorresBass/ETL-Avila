"""Unit tests for shared person provisional keys."""

from __future__ import annotations

import unittest

from person_upsert import fold_person_name, provisional_key_for_name


class PersonUpsertKeyTests(unittest.TestCase):
    def test_name_scoped_key(self):
        self.assertEqual(
            provisional_key_for_name("María Pérez"),
            provisional_key_for_name("maria perez"),
        )
        self.assertTrue(provisional_key_for_name("Ana Lopez").startswith("name:"))

    def test_fold_collapses_whitespace(self):
        self.assertEqual(fold_person_name("  Ana   Lopez "), "ana lopez")


if __name__ == "__main__":
    unittest.main()
