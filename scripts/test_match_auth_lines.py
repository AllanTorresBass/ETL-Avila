"""Authorization line → invoice scoring (anonymized)."""

from __future__ import annotations

import datetime as dt
import unittest

from match_auth_lines import Invoice, Line, decide, line_date, norm_clave, rank_line

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


if __name__ == "__main__":
    unittest.main()
