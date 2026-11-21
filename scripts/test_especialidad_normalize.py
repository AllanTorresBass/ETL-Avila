"""Especialidad normalizer: L1 cleaning, L2 matching, L3 kinds, catalog integrity."""

from __future__ import annotations

import unittest

from especialidad_normalize import (
    best_specialty,
    clean_tokens,
    default_catalog,
    degree_of,
    first_procedure,
    match_token,
    normalize_text,
    osa_distance,
)


def _one(raw: str, context: str = "doctor_title"):
    matches = [m for m in normalize_text(raw, context) if m.term]
    return matches[0] if matches else None


class CleanTokens(unittest.TestCase):
    def test_folds_accents_gender_and_universities(self):
        tokens, university = clean_tokens("Dra. Endocrinóloga (ULA)")
        self.assertEqual(tokens, ["DRA", "ENDOCRINOLOGO"])
        self.assertEqual(university, "ULA")

    def test_cirujano_with_university_becomes_degree_phrase(self):
        tokens, _ = clean_tokens("CIRUJANO UNEFM")
        self.assertEqual(tokens, ["MEDICO", "CIRUJANO"])

    def test_misread_medico_is_repaired(self):
        tokens, _ = clean_tokens("MEDIGO CIRUJANO")
        self.assertEqual(tokens, ["MEDICO", "CIRUJANO"])


class LexicalMatch(unittest.TestCase):
    def test_exact(self):
        match = _one("CARDIOLOGIA", "label")
        self.assertEqual((match.method, match.especialidad), ("exact", "cardiologia"))

    def test_phrase_beats_bare_word(self):
        match = _one("CIRUGIA VASCULAR", "label")
        self.assertEqual((match.method, match.especialidad), ("phrase", "cirugia_vascular"))

    def test_suffix_fragment(self):
        match = _one("ROENTEROLOGO")
        self.assertEqual((match.method, match.especialidad), ("suffix_fragment", "gastroenterologia"))

    def test_ambiguous_fragment_is_unmatched(self):
        # ...MATOLOGIA ends both TRAUMATOLOGIA and HEMATOLOGIA.
        match = match_token("MATOLOGIA", "label", default_catalog())
        self.assertTrue(match is None or match.term is None or match.method != "suffix_fragment")

    def test_fuzzy_ocr_misspellings(self):
        for raw, code in (
            ("INTEMISTA", "medicina_interna"),
            ("TARUMATOLOGIA", "traumatologia"),
            ("GASTROENTOROLOGIA", "gastroenterologia"),
            ("CASTROENTEROLOGO", "gastroenterologia"),
            ("OFTAMOLOGIA", "oftalmologia"),
        ):
            with self.subTest(raw=raw):
                match = _one(raw)
                self.assertEqual(match.method, "fuzzy")
                self.assertEqual(match.especialidad, code)

    def test_fuzzy_tie_is_rejected(self):
        # One edit from both NEFROLOGIA and NEUROLOGIA.
        match = match_token("NEXROLOGIA", "label", default_catalog())
        self.assertEqual(match.method, "none")
        self.assertIsNone(match.term)

    def test_glued_prefix_split(self):
        self.assertEqual(_one("ESPECIALIDADUROLOGIA", "label").especialidad, "urologia")
        self.assertEqual(_one("MEDICOINTERNISTA").especialidad, "medicina_interna")
        self.assertEqual(_one("CONSULTATRAUMATOLOGIA", "fiscal_line").especialidad, "traumatologia")

    def test_gender_fold(self):
        self.assertEqual(_one("ENDOCRINOLOGA").especialidad, "endocrinologia")

    def test_synonyms_share_a_code(self):
        self.assertEqual(_one("NEUMOLOGIA", "label").especialidad, _one("NEUMONOLOGIA", "label").especialidad)


class Kinds(unittest.TestCase):
    def test_medico_cirujano_is_a_degree(self):
        matches = normalize_text("MEDICO CIRUJANO", "doctor_title")
        self.assertEqual(degree_of(matches).degree, "medico_cirujano")
        self.assertIsNone(best_specialty(matches))

    def test_cirujano_with_university_is_a_degree(self):
        matches = normalize_text("CIRUJANO ULA", "doctor_title")
        degree = degree_of(matches)
        self.assertEqual((degree.degree, degree.university), ("medico_cirujano", "ULA"))
        self.assertIsNone(best_specialty(matches))

    def test_degree_and_specialty_on_one_line(self):
        matches = normalize_text("MEDICO CIRUJANO - CARDIOLOGO", "doctor_title")
        self.assertEqual(best_specialty(matches).especialidad, "cardiologia")

    def test_stop_words(self):
        for raw in ("ESPECIALISTA", "BAUTISTA", "SINTOMATOLOGIA"):
            with self.subTest(raw=raw):
                match = _one(raw)
                self.assertEqual(match.kind, "stop")
                self.assertFalse(match.is_specialty)

    def test_role_is_not_a_specialty(self):
        match = _one("ECOGRAFISTA")
        self.assertEqual(match.kind, "role")
        self.assertFalse(match.is_specialty)

    def test_procedure(self):
        matches = normalize_text("VIDEOCOLONOSCOPIA", "report_title")
        self.assertEqual(first_procedure(matches).procedimiento, "colonoscopia")

    def test_adjective_only_in_report_title(self):
        self.assertIsNone(best_specialty(normalize_text("INFORME MEDICO CARDIOLOGICO", "label")))
        self.assertEqual(
            best_specialty(normalize_text("INFORME MEDICO CARDIOLOGICO", "report_title")).especialidad,
            "cardiologia",
        )

    def test_adjective_in_service_line(self):
        matches = normalize_text("CONSULTA GINECOLOGICA, ULTRASONIDO TRANSVAGINAL", "auth_line")
        self.assertEqual(best_specialty(matches).especialidad, "ginecologia_obstetricia")
        self.assertEqual(first_procedure(matches).procedimiento, "ecografia")

    def test_subespecialidad_beats_parent(self):
        matches = normalize_text("CIRUGIA GENERAL CIRUGIA VASCULAR", "doctor_title")
        self.assertEqual(best_specialty(matches).especialidad, "cirugia_vascular")

    def test_unshaped_words_are_ignored(self):
        self.assertEqual(normalize_text("PACIENTE MASCULINO DE AÑOS", "label"), [])

    def test_unknown_shaped_word_is_backlog(self):
        matches = normalize_text("XYLOFONOLOGIA", "label")
        self.assertEqual([m.method for m in matches], ["none"])


class Distance(unittest.TestCase):
    def test_transposition_counts_once(self):
        self.assertEqual(osa_distance("CARDIOLOGIA", "CARDIOLOIGA", 2), 1)


class CatalogIntegrity(unittest.TestCase):
    def test_targets_and_hierarchy(self):
        catalog = default_catalog()
        for code, row in catalog.especialidades.items():
            self.assertIn(row["area"], catalog.areas, code)
            if row["level"] == "2":
                parent = catalog.especialidades.get(row["parent_code"])
                self.assertIsNotNone(parent, code)
                self.assertEqual(parent["level"], "1", code)
                self.assertEqual(parent["area"], row["area"], code)
            else:
                self.assertEqual(row["parent_code"], "", code)
        for code, row in catalog.procedimientos.items():
            self.assertIn(row["especialidad_code"], catalog.especialidades, code)
        terms = list(catalog.single.values()) + list(catalog.phrases.values())
        for term in terms:
            if term.kind in ("discipline", "practitioner", "adjective"):
                self.assertIn(term.especialidad, catalog.especialidades, term.term)
            if term.kind == "procedure":
                self.assertIn(term.procedimiento, catalog.procedimientos, term.term)


if __name__ == "__main__":
    unittest.main()
