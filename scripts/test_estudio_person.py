"""Patient rule for a study row. One beneficiario, otherwise one titular."""

import unittest

from estudio_extract import _status, resolve_patient


class ResolvePatient(unittest.TestCase):
    def test_one_beneficiario(self):
        self.assertEqual(resolve_patient(["beneficiario"], ["titular"]), ("beneficiario", "linked_beneficiario"))

    def test_self_titular(self):
        self.assertEqual(resolve_patient([], ["titular"]), ("titular", "linked_self"))

    def test_two_beneficiarios(self):
        self.assertEqual(resolve_patient(["one", "two"], ["titular"]), (None, "review_ambiguous"))

    def test_nobody(self):
        person, cohort = resolve_patient([], [])
        self.assertIsNone(person)
        self.assertEqual(cohort, "nobody")

    def test_repeated_beneficiario_is_still_one_patient(self):
        self.assertEqual(resolve_patient(["same", "same"], []), ("same", "linked_beneficiario"))

    def test_status_follows_the_patient_cohort(self):
        self.assertEqual(_status("estudio", "electrocardiograma", "linked_beneficiario"), "matched")
        self.assertEqual(_status("estudio", None, "linked_self"), "unmatched")
        self.assertEqual(_status("estudio", "electrocardiograma", "review_ambiguous"), "review")
        self.assertEqual(_status("estudio", "electrocardiograma", "nobody"), "review")
        self.assertEqual(_status("consulta", None, "nobody"), "matched")


if __name__ == "__main__":
    unittest.main()
