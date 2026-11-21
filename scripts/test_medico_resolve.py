"""Unit tests for medico_resolve (fake reports, no Neon)."""

from __future__ import annotations

import unittest
from collections import Counter

from medico_resolve import (
    link_patient,
    link_status,
    name_match,
    name_tokens,
    primary_especialidad,
    resolve,
    visit_especialidad,
)


def doctor(name=None, mpps=None, role="firmante", zone="footer", rule="stamp_dr", esp=None, doc="d1"):
    return {
        "title": "dra",
        "name": name.title() if name else None,
        "name_folded": name,
        "mpps": mpps,
        "colegio": None,
        "rif": None,
        "zone": zone,
        "role": role,
        "rule_id": rule,
        "especialidad": esp,
        "degree": None,
        "degree_university": None,
        "document_id": doc,
    }


def report(doc, doctors=(), terms=(), patient=None, persons=(), kind="informe", fingerprint=None, diagnosis="X"):
    return {
        "extractor_version": "clinical-1",
        "primary_document_id": doc,
        "document_ids": [doc],
        "report_kind": kind,
        "source_ref": f"F/{doc}.pdf#1",
        "invoice_id": f"inv-{doc}",
        "doctors": list(doctors),
        "terms": list(terms),
        "patient": patient or {"name": None, "ci": None},
        "encounter_date": None,
        "diagnosis": diagnosis,
        "fingerprint": fingerprint or f"fp-{doc}",
        "invoice_persons": list(persons),
        "fiscal_terms": [],
        "auth_especialidades": [],
    }


TITULAR = {"person_id": "p-t", "role": "titular", "full_name": "JUAN PEREZ GOMEZ", "identity_number": "11222333"}
CHILD = {"person_id": "p-b", "role": "beneficiario", "full_name": "LUIS PEREZ DIAZ", "identity_number": None}


class NameMatchTests(unittest.TestCase):
    def test_subset_and_one_ocr_edit(self):
        self.assertTrue(name_match(name_tokens("ANA TORRES"), name_tokens("ANA MARIA TORRES MENDEZ")))
        self.assertTrue(name_match(name_tokens("ANA TORRFS MENDEZ"), name_tokens("ANA TORRES MENDEZ")))

    def test_single_token_never_matches(self):
        self.assertFalse(name_match(name_tokens("TORRES"), name_tokens("ANA TORRES")))

    def test_different_people(self):
        self.assertFalse(name_match(name_tokens("ANA TORRES"), name_tokens("ANA RIVAS")))


class PrimaryEspecialidadTests(unittest.TestCase):
    def test_subspecialty_replaces_parent(self):
        self.assertEqual(primary_especialidad(Counter({"medicina_interna": 6, "cardiologia": 3})), "cardiologia")

    def test_weak_subspecialty_does_not(self):
        self.assertEqual(primary_especialidad(Counter({"medicina_interna": 10, "cardiologia": 2})), "medicina_interna")


class PatientLinkTests(unittest.TestCase):
    def test_ci_exact(self):
        r = report("a", patient={"name": None, "ci": "V-11.222.333"}, persons=[TITULAR, CHILD])
        self.assertEqual(link_patient(r)[:2], ("p-t", "ci_exact"))

    def test_name_on_invoice_beats_roles(self):
        r = report("a", patient={"name": "Luis Perez", "ci": None}, persons=[TITULAR, CHILD])
        self.assertEqual(link_patient(r)[:2], ("p-b", "name_on_invoice"))

    def test_sole_beneficiario_without_page_identity(self):
        self.assertEqual(link_patient(report("a", persons=[TITULAR, CHILD]))[:2], ("p-b", "sole_beneficiario"))

    def test_self_visit(self):
        self.assertEqual(link_patient(report("a", persons=[TITULAR]))[:2], ("p-t", "self_visit"))

    def test_foreign_name_goes_to_review(self):
        r = report("a", patient={"name": "Rosa Blanco Rivas", "ci": None}, persons=[TITULAR, CHILD])
        person, rule, candidates = link_patient(r)
        self.assertEqual((person, rule), (None, "review"))
        self.assertEqual(candidates, ["p-b", "p-t"])

    def test_no_persons_no_rule(self):
        self.assertEqual(link_patient(report("a"))[:2], (None, None))


class VisitEspecialidadTests(unittest.TestCase):
    def test_page_beats_medico_primary(self):
        terms = [{"context": "doctor_title", "kind": "practitioner", "especialidad": "pediatria"}]
        self.assertEqual(visit_especialidad(report("a", terms=terms), "neurologia", None), ("pediatria", "doctor_title"))

    def test_medico_primary_then_procedure_then_kind(self):
        self.assertEqual(visit_especialidad(report("a"), "neurologia", None), ("neurologia", "medico_primary"))
        self.assertEqual(visit_especialidad(report("a"), None, "ecocardiograma"), ("cardiologia", "procedure"))
        self.assertEqual(visit_especialidad(report("a", kind="laboratorio"), None, None), ("laboratorio_clinico", "procedure"))

    def test_status(self):
        self.assertEqual(link_status(False, "ci_exact", True, True, True), "complete")
        self.assertEqual(link_status(False, "review", False, True, True), "review")
        self.assertEqual(link_status(True, "ci_exact", True, True, True), "duplicate")
        self.assertEqual(link_status(False, None, False, False, False), "unmatched")


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.reports = [
            report("a", [doctor("ANA TORRES MENDEZ", "222222", esp="cardiologia")], persons=[TITULAR]),
            report("b", [doctor("ANA TORRES MENDEZ", "222222", esp="medicina_interna")], persons=[TITULAR]),
            report("c", [doctor("ANA TORRES", rule="dr_line", zone="header")], persons=[TITULAR]),
            report("d", [doctor("PEDRO RUIZ SOTO", rule="dr_line", zone="header")], persons=[TITULAR]),
            report("e", [doctor("JOSE LARA", rule="dr_line", zone="body", role="referido")], persons=[TITULAR]),
            report("f", [doctor("ANA TORRES MENDEZ", "222222")], persons=[TITULAR], fingerprint="fp-a"),
        ]
        self.records, self.stats = resolve(self.reports)
        self.by_type = {}
        for record in self.records:
            self.by_type.setdefault(record["type"], []).append(record)

    def test_clusters(self):
        keys = sorted(m["key"] for m in self.by_type["medico"])
        self.assertEqual(keys, ["mpps:222222", "name:PEDRO RUIZ SOTO"])

    def test_unlicensed_name_joins_mpps_cluster(self):
        atencion = {a["primary_document_id"]: a for a in self.by_type["atencion"]}
        self.assertEqual(atencion["c"]["medico_key"], "mpps:222222")
        self.assertIsNone(atencion["e"]["medico_key"])

    def test_duplicate_fingerprint(self):
        atencion = {a["primary_document_id"]: a for a in self.by_type["atencion"]}
        self.assertEqual(atencion["f"]["link_status"], "duplicate")
        self.assertEqual(atencion["f"]["duplicate_of_document"], "a")

    def test_mpps_conflict_review(self):
        reports = [
            report(str(i), [doctor(name, "333333")]) for i, name in enumerate(["ROSA DIAZ", "ROSA DIAZ", "LUIS VERA", "LUIS VERA"])
        ]
        records, _ = resolve(reports)
        kinds = [r["kind"] for r in records if r["type"] == "review"]
        self.assertIn("medico_mpps_conflict", kinds)

    def test_two_mpps_same_name_opens_duplicate(self):
        reports = [report("x", [doctor("ROSA DIAZ PEREZ", "111111")]), report("y", [doctor("ROSA DIAZ PEREZ", "444444")])]
        records, _ = resolve(reports)
        self.assertEqual([r["kind"] for r in records if r["type"] == "review"], ["medico_duplicate"])


if __name__ == "__main__":
    unittest.main()
