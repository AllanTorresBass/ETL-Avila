"""Decisions for cédulas that have no factura role."""

from __future__ import annotations

import unittest

from workbook_enrichment.orphan_cedulas import (
    LEAVE,
    LINK_BENEFICIARIO,
    OCCUPIED,
    PROMOTE_TITULAR,
    REVIEW_DUPLICATE,
    decide_never_linked,
    decide_orphan_row,
    one_digit_apart,
    shares_name_token,
)

TITULAR = "11222333"
PATIENT = "44555666"
OTHER = "99888777"


def _row(**extra):
    base = {
        "invoice_number": "100",
        "titular_ci": TITULAR,
        "titular_name": "JUAN PEREZ",
        "beneficiario_ci": None,
        "beneficiario_name": None,
    }
    base.update(extra)
    return base


def _decide(row, **kwargs):
    args = {
        "invoice_found": True,
        "titular_ci": None,
        "beneficiario_cis": set(),
        "eligible_cis": {TITULAR},
    }
    args.update(kwargs)
    return decide_orphan_row(row, **args)


class OrphanCedulaDecisionTests(unittest.TestCase):
    def test_empty_titular_slot_links_titular(self):
        decisions = _decide(_row())
        self.assertEqual(
            [(d.action, d.ci, d.reason) for d in decisions],
            [("link_titular", TITULAR, "titular_slot_empty")],
        )

    def test_occupied_titular_slot_is_a_review(self):
        decisions = _decide(_row(), titular_ci=OTHER)
        self.assertEqual(
            [(d.action, d.reason) for d in decisions],
            [("review", "packet_conflict")],
        )

    def test_truth_removed_person_is_not_linked(self):
        decisions = _decide(
            _row(),
            eligible_cis=set(),
            truth_removed_cis={TITULAR},
        )
        self.assertEqual(
            [(d.action, d.reason) for d in decisions],
            [("skip", "truth_blocked")],
        )

    def test_truth_removed_wins_over_an_empty_slot(self):
        decisions = _decide(_row(), truth_removed_cis={TITULAR})
        self.assertEqual(decisions[0].reason, "truth_blocked")
        self.assertNotEqual(decisions[0].action, "link_titular")

    def test_missing_factura_number(self):
        decisions = _decide(_row(invoice_number=None))
        self.assertEqual(decisions[0].reason, "no_factura_number")

    def test_factura_not_loaded(self):
        decisions = _decide(_row(), invoice_found=False)
        self.assertEqual(decisions[0].reason, "factura_not_loaded")

    def test_self_row_links_one_titular(self):
        decisions = _decide(
            _row(beneficiario_ci=TITULAR, beneficiario_name="JUAN PEREZ"),
        )
        self.assertEqual([d.action for d in decisions], ["link_titular"])

    def test_pair_links_titular_and_beneficiario_when_both_slots_are_empty(self):
        decisions = _decide(
            _row(beneficiario_ci=PATIENT, beneficiario_name="MARIA PEREZ"),
            eligible_cis={TITULAR, PATIENT},
        )
        self.assertEqual(
            [(d.action, d.ci, d.reason) for d in decisions],
            [
                ("link_titular", TITULAR, "titular_slot_empty"),
                ("link_beneficiario", PATIENT, "beneficiario_slot_empty"),
            ],
        )

    def test_pair_links_only_the_beneficiario_when_the_titular_is_already_there(self):
        decisions = _decide(
            _row(beneficiario_ci=PATIENT, beneficiario_name="MARIA PEREZ"),
            titular_ci=TITULAR,
            eligible_cis={PATIENT},
        )
        self.assertEqual(
            [(d.action, d.ci) for d in decisions],
            [("link_beneficiario", PATIENT)],
        )

    def test_beneficiario_waits_until_a_titular_exists(self):
        decisions = _decide(
            _row(beneficiario_ci=PATIENT, beneficiario_name="MARIA PEREZ"),
            eligible_cis={PATIENT},
        )
        self.assertEqual(decisions[0].reason, "beneficiario_needs_titular")

    def test_same_titular_is_already_linked(self):
        decisions = _decide(_row(), titular_ci=TITULAR)
        self.assertEqual(decisions[0].reason, "already_linked")

    def test_does_not_upgrade_an_existing_beneficiario_into_titular(self):
        decisions = _decide(_row(), beneficiario_cis={TITULAR})
        self.assertEqual(decisions[0].reason, "already_linked")
        self.assertNotEqual(decisions[0].action, "link_titular")

    def test_occupied_sentinel_is_a_conflict(self):
        decisions = _decide(_row(), titular_ci=OCCUPIED)
        self.assertEqual(decisions[0].action, "review")

    def test_open_ci_conflict_is_skipped(self):
        decisions = _decide(_row(), open_conflict_cis={TITULAR})
        self.assertEqual(decisions[0].reason, "open_ci_conflict")


class NeverLinkedDecisionTests(unittest.TestCase):
    def test_patient_on_its_own_factura_links_beneficiario(self):
        action = decide_never_linked(
            PATIENT,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="100",
        )
        self.assertEqual(action, LINK_BENEFICIARIO)

    def test_range_bundle_is_not_a_link_target(self):
        action = decide_never_linked(
            PATIENT,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="range:18030-18134",
        )
        self.assertEqual(action, LEAVE)

    def test_span_without_the_range_prefix_is_not_a_link_target(self):
        action = decide_never_linked(
            PATIENT,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="18030-18134",
        )
        self.assertEqual(action, LEAVE)

    def test_empty_titular_slot_promotes(self):
        action = decide_never_linked(
            TITULAR,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="100",
            titular_slot_empty=True,
        )
        self.assertEqual(action, PROMOTE_TITULAR)

    def test_occupied_titular_slot_stays_unlinked(self):
        action = decide_never_linked(
            TITULAR,
            fiscal_titular_ci=TITULAR,
            invoice_number="100",
            titular_slot_empty=False,
        )
        self.assertEqual(action, LEAVE)

    def test_shared_name_twin_is_a_review_and_stops_the_page(self):
        action = decide_never_linked(
            PATIENT,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="100",
            twin_shares_name=True,
        )
        self.assertEqual(action, REVIEW_DUPLICATE)

    def test_different_name_is_not_a_review(self):
        self.assertFalse(shares_name_token("JUAN PEREZ", "MARIA LOPEZ"))
        action = decide_never_linked(
            PATIENT,
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci=PATIENT,
            invoice_number="100",
            twin_shares_name=False,
        )
        self.assertEqual(action, LINK_BENEFICIARIO)

    def test_six_digit_cedula_stays_unlinked(self):
        action = decide_never_linked(
            "123456",
            fiscal_titular_ci=TITULAR,
            fiscal_patient_ci="123456",
            invoice_number="100",
            twin_shares_name=True,
        )
        self.assertEqual(action, LEAVE)

    def test_mention_without_a_fiscal_role_stays_unlinked(self):
        action = decide_never_linked("11222333", invoice_number="100")
        self.assertEqual(action, LEAVE)

    def test_one_digit_and_a_shared_token(self):
        self.assertTrue(one_digit_apart("11222333", "11222334"))
        self.assertFalse(one_digit_apart("123456", "123457"))
        self.assertTrue(shares_name_token("María López", "MARIA PEREZ LOPEZ"))


if __name__ == "__main__":
    unittest.main()
