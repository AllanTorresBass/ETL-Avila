import datetime as dt
import unittest
from unittest.mock import MagicMock

import provenance


class ValueHashTests(unittest.TestCase):
    def test_none_and_blank_hash_to_none(self):
        self.assertIsNone(provenance.value_hash(None))
        self.assertIsNone(provenance.value_hash("   "))

    def test_whitespace_and_case_insensitive(self):
        self.assertEqual(
            provenance.value_hash("JUAN  PEREZ"), provenance.value_hash("juan perez")
        )

    def test_dates_hash_by_iso(self):
        self.assertEqual(
            provenance.value_hash(dt.date(1990, 1, 2)), provenance.value_hash("1990-01-02")
        )

    def test_hash_is_short_and_not_plaintext(self):
        h = provenance.value_hash("11222333")
        self.assertEqual(len(h), 16)
        self.assertNotIn("11222333", h)


class RecordTests(unittest.TestCase):
    def test_unchanged_value_is_noop(self):
        cur = MagicMock()
        self.assertFalse(
            provenance.record(
                cur, entity="person", entity_id="p", field="phone", old="1", new="1", rule_id="r"
            )
        )
        cur.execute.assert_not_called()

    def test_change_uses_source_context(self):
        cur = MagicMock()
        with provenance.source("workbook", "book.xlsx:Hoja1:4"):
            self.assertTrue(
                provenance.record(
                    cur, entity="person", entity_id="p", field="birth_date",
                    old=None, new="1990-01-02", rule_id="upsert_by_ci",
                )
            )
        params = cur.execute.call_args[0][1]
        self.assertEqual(params[5], "workbook")
        self.assertEqual(params[6], "book.xlsx:Hoja1:4")
        self.assertNotIn("1990-01-02", params)

    def test_without_context_defaults_to_derived(self):
        cur = MagicMock()
        provenance.record(
            cur, entity="person", entity_id="p", field="phone", old=None, new="x", rule_id="r"
        )
        self.assertEqual(cur.execute.call_args[0][1][5], "derived")

    def test_unknown_source_kind_rejected(self):
        with self.assertRaises(ValueError):
            with provenance.source("rumor"):
                pass


class ReviewTests(unittest.TestCase):
    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            provenance.open_review(MagicMock(), kind="whatever", dedupe_key="k")

    def test_open_review_upserts_on_dedupe_key(self):
        cur = MagicMock()
        provenance.open_review(cur, kind="ci_conflict", dedupe_key="ci_conflict:i:p", invoice_id="i")
        sql = cur.execute.call_args[0][0]
        self.assertIn("ON CONFLICT (dedupe_key)", sql)
        self.assertIn("status = 'open'", sql)


if __name__ == "__main__":
    unittest.main()
