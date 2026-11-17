"""Golden pairs for the duplicate resolver (anonymized)."""

from __future__ import annotations

import datetime as dt
import unittest

from identity_resolver import (
    Person,
    candidate_pairs,
    decide,
    name_score,
    phonetic,
    score_pair,
    survivor_of,
    token_similarity,
)

DOB = dt.date(2012, 5, 6)


def p(pid, name, **kw):
    return Person(pid, name, **kw)


class TokenTests(unittest.TestCase):
    def test_phonetic_variants(self):
        self.assertEqual(phonetic("gonzales"), phonetic("gonzalez"))
        self.assertEqual(phonetic("velasquez"), phonetic("belazquez"))
        self.assertEqual(phonetic("hernandez"), phonetic("ernandes"))

    def test_one_letter_ocr_slip(self):
        self.assertGreaterEqual(token_similarity("josues", "josuas"), 0.9)

    def test_unrelated_tokens(self):
        self.assertEqual(token_similarity("maria", "pedro"), 0.0)

    def test_subset_name_scores_below_auto(self):
        self.assertLess(name_score(["juan", "perez"], ["juan", "perez", "gomez"]), 0.95)


class GoldenPairTests(unittest.TestCase):
    def test_spelling_variant_child_same_dob_auto_merges(self):
        """Mirrors the case of one child entered twice with a one-letter OCR slip."""
        a = p("a", "JOSUES MANUEL PERES GIL", birth_date=DOB, titulars={"t1"}, invoices={"i1"}, roles={"i1": "beneficiario"})
        b = p("b", "JOSUAS MANUEL PEREZ GIL", birth_date=DOB, titulars={"t1"}, invoices={"i2"}, roles={"i2": "beneficiario"})
        s = score_pair(a, b)
        self.assertEqual(decide(s), "merge")

    def test_variant_without_dob_goes_to_review(self):
        s = score_pair(p("a", "JOSUES MANUEL PERES GIL"), p("b", "JOSUAS MANUEL PEREZ GIL"))
        self.assertEqual(decide(s), "review")

    def test_different_ci_never_pairs(self):
        self.assertIsNone(
            score_pair(p("a", "JUAN PEREZ", ci="11222333"), p("b", "JUAN PEREZ", ci="44555666"))
        )

    def test_different_dob_is_not_merged(self):
        s = score_pair(
            p("a", "JUAN PEREZ GOMEZ", birth_date=DOB),
            p("b", "JUAN PEREZ GOMEZ", birth_date=dt.date(1980, 1, 1)),
        )
        self.assertNotEqual(decide(s), "merge")

    def test_parent_and_child_same_name_on_one_invoice_not_auto_merged(self):
        a = p("a", "JUAN PEREZ GOMEZ", birth_date=DOB, invoices={"i1"}, roles={"i1": "titular"})
        b = p("b", "JUAN PEREZ GOMEZ", birth_date=DOB, invoices={"i1"}, roles={"i1": "beneficiario"})
        self.assertEqual(decide(score_pair(a, b)), "review")

    def test_survivor_prefers_ci_then_links(self):
        a = p("a", "JUAN PEREZ", invoices={"i1", "i2"})
        b = p("b", "JUAN PEREZ", ci="11222333")
        self.assertEqual(survivor_of(a, b)[0].id, "b")

    def test_blocks_find_variant_pair(self):
        people = {
            "a": p("a", "JOSUES MANUEL PERES GIL"),
            "b": p("b", "JOSUAS MANUEL PEREZ GIL"),
            "c": p("c", "MARIA LOPEZ"),
        }
        self.assertIn(("a", "b"), candidate_pairs(people))
        self.assertNotIn(("a", "c"), candidate_pairs(people))


if __name__ == "__main__":
    unittest.main()
