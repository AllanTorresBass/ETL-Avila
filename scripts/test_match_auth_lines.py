"""Authorization line → invoice scoring (anonymized)."""

from __future__ import annotations

import datetime as dt
import unittest

from match_auth_lines import (
    Invoice,
    Line,
    candidate_pool,
    decide,
    line_date,
    norm_clave,
    rank_line,
    unlinked_status,
)

D = dt.date(2025, 3, 1)


def line(**kw):
    base = dict(id="l1", person_id="p1", clave=None, account="seguros_miranda", when=D, amounts=(), words=set())
    base.update(kw)
    return Line(**base)


def inv(iid, **kw):
    base = dict(id=iid, account="seguros_miranda", issue_date=D + dt.timedelta(days=10), clave=None, totals=())
    base.update(kw)
    people = base.pop("people", {"p1"})
    out = Invoice(**base)
    out.people = set(people)
    return out


class MatcherTests(unittest.TestCase):
    def test_norm_clave(self):
        self.assertEqual(norm_clave("RMS-0012345"), "12345")
        self.assertIsNone(norm_clave("12"))

    def test_person_plus_date_single_invoice_links(self):
        self.assertEqual(decide(rank_line(line(), [inv("i1")])), "link")

    def test_two_equal_invoices_go_to_review(self):
        self.assertEqual(decide(rank_line(line(), [inv("i1"), inv("i2")])), "review")

    def test_clave_breaks_the_tie(self):
        ranked = rank_line(line(clave="12345"), [inv("i1"), inv("i2", clave="12345")])
        self.assertEqual(ranked[0][1], "i2")
        self.assertEqual(decide(ranked), "link")

    def test_issue_before_request_is_penalized(self):
        ranked = rank_line(line(), [inv("i1", issue_date=D - dt.timedelta(days=30))])
        self.assertEqual(decide(ranked), "none")

    def test_authorization_a_year_before_issue_is_not_reviewed(self):
        ranked = rank_line(line(), [inv("i1", issue_date=D + dt.timedelta(days=400))])
        self.assertEqual(decide(ranked), "none")

    def test_other_account_excluded(self):
        self.assertEqual(rank_line(line(), [inv("i1", account="la_previsora")]), [])

    def test_amount_and_clave_without_person_links(self):
        ranked = rank_line(
            line(person_id=None, clave="999888", amounts=(150.0,)),
            [inv("i1", clave="999888", totals=(151.0,), people=set())],
        )
        self.assertEqual(decide(ranked), "link")

    def test_placeholder_workbook_dates_are_ignored(self):
        self.assertIsNone(line_date(dt.date(1899, 12, 30), None))
        self.assertEqual(line_date(dt.date(1900, 1, 1), D), D)

    def test_titular_on_invoice_is_a_signal(self):
        ranked = rank_line(line(person_id="kid", titular_id="p1"), [inv("i1")])
        self.assertIn("titular", ranked[0][2])
        self.assertEqual(decide(ranked), "review")
        with_amount = rank_line(
            line(person_id="kid", titular_id="p1", amounts=(150.0,)), [inv("i1", totals=(150.0,))]
        )
        self.assertEqual(decide(with_amount), "link")

    def test_titular_does_not_add_to_person_signal(self):
        ranked = rank_line(line(titular_id="p1"), [inv("i1")])
        self.assertIn("person", ranked[0][2])
        self.assertNotIn("titular", ranked[0][2])

    def test_period_month_is_a_weak_date(self):
        undated = line(when=None, period=dt.date(2025, 3, 1))
        ranked = rank_line(undated, [inv("i1", issue_date=dt.date(2025, 4, 10))])
        self.assertIn("period:1m", ranked[0][2])
        self.assertEqual(decide(ranked), "review")

    def test_issue_before_period_month_is_penalized(self):
        undated = line(when=None, period=dt.date(2025, 3, 1))
        ranked = rank_line(undated, [inv("i1", issue_date=dt.date(2025, 2, 10))])
        self.assertEqual(decide(ranked), "none")

    def test_exact_date_wins_over_period(self):
        ranked = rank_line(line(period=dt.date(2020, 1, 1)), [inv("i1")])
        self.assertFalse(any(s.startswith("period") for s in ranked[0][2]))

    def test_candidate_pool_includes_titular_facturas(self):
        kid = line(person_id="kid", titular_id="p1")
        pool = candidate_pool(kid, {"p1": [inv("i1")]}, {})
        self.assertEqual(list(pool), ["i1"])

    def test_unlinked_status_reasons(self):
        best = [(0.4, "i1", ["person"])]
        self.assertEqual(unlinked_status(line(person_id=None), [], "none"), "no_person")
        self.assertEqual(unlinked_status(line(), [], "none"), "no_candidate")
        self.assertEqual(unlinked_status(line(), best, "none"), "low_score")
        self.assertEqual(unlinked_status(line(), best, "review"), "review")

    def test_factura_long_after_period_is_stale(self):
        undated = line(when=None, period=dt.date(2023, 3, 1))
        ranked = rank_line(undated, [inv("i1", issue_date=dt.date(2025, 2, 10))])
        self.assertIn("period:stale", ranked[0][2])
        self.assertEqual(decide(ranked), "none")


if __name__ == "__main__":
    unittest.main()
