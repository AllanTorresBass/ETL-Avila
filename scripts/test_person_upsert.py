"""Unit tests for shared person provisional keys."""

from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

from person_upsert import _flag_dob_conflict, fold_person_name, merge_person, provisional_key_for_name


class PersonUpsertKeyTests(unittest.TestCase):
    def test_name_scoped_key(self):
        self.assertEqual(
            provisional_key_for_name("María Pérez"),
            provisional_key_for_name("maria perez"),
        )
        self.assertTrue(provisional_key_for_name("Ana Lopez").startswith("name:"))

    def test_fold_collapses_whitespace(self):
        self.assertEqual(fold_person_name("  Ana   Lopez "), "ana lopez")


def _person(pid, **kw):
    base = {
        "id": pid,
        "identity_type": "unknown",
        "identity_number": None,
        "full_name": "JUAN PEREZ",
        "birth_date": None,
        "phone": None,
        "address": None,
    }
    base.update(kw)
    return base


class MergePersonTests(unittest.TestCase):
    def _cur(self, survivor, alias):
        cur = MagicMock()
        cur.fetchall.return_value = [survivor, alias]
        cur.rowcount = 1
        return cur

    def _sql(self, cur):
        return [c.args[0] for c in cur.execute.call_args_list]

    def test_rewires_links_and_deletes_alias(self):
        cur = self._cur(_person("s"), _person("a", phone="04140000000"))
        with patch("person_upsert.provenance.record"):
            out = merge_person(cur, "s", "a", reason="t")
        sql = " ".join(self._sql(cur))
        self.assertIn("UPDATE avila.document SET person_id", sql)
        self.assertIn("UPDATE avila.authorization_line SET person_id", sql)
        self.assertIn("DELETE FROM avila.person", sql)
        self.assertEqual(out["invoice_person"], 1)
        fill_call = [c for c in cur.execute.call_args_list if "SET phone" in c.args[0]]
        self.assertEqual(len(fill_call), 1)

    def test_alias_ci_moves_to_survivor(self):
        cur = self._cur(_person("s"), _person("a", identity_type="cedula", identity_number="11222333"))
        with patch("person_upsert.provenance.record"):
            merge_person(cur, "s", "a")
        fill = [c for c in cur.execute.call_args_list if "identity_number = %s" in c.args[0]]
        self.assertEqual(len(fill), 1)
        self.assertIn("11222333", fill[0].args[1])

    def test_conflicting_ci_refuses(self):
        cur = self._cur(
            _person("s", identity_number="11222333"), _person("a", identity_number="44555666")
        )
        with self.assertRaises(ValueError):
            merge_person(cur, "s", "a")

    def test_same_id_is_noop(self):
        cur = MagicMock()
        self.assertEqual(merge_person(cur, "s", "s"), {})
        cur.execute.assert_not_called()


class DobConflictTests(unittest.TestCase):
    def test_different_dob_opens_review(self):
        with patch("person_upsert.provenance.open_review") as review:
            _flag_dob_conflict(MagicMock(), "p", dt.date(1980, 1, 1), dt.date(2015, 3, 2))
        review.assert_called_once()
        self.assertEqual(review.call_args.kwargs["kind"], "dob_conflict")

    def test_same_or_missing_dob_is_silent(self):
        with patch("person_upsert.provenance.open_review") as review:
            _flag_dob_conflict(MagicMock(), "p", dt.date(1980, 1, 1), dt.date(1980, 1, 1))
            _flag_dob_conflict(MagicMock(), "p", None, dt.date(1980, 1, 1))
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
