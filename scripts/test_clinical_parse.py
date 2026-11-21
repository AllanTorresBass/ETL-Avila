"""Informe médico parser: doctor stamps, especialidad lines, patient block, diagnosis."""

from __future__ import annotations

import unittest

from clinical_parse import (
    group_report_pages,
    page_procedure,
    parse_page,
    referred_specialty,
    visit_specialty,
)

GPS_FOOTER = """G.P.S. GESTION PROFESIONAL DE SALUD RIF J-41029281-4
INFORME MÉDICO
PACIENTE: JUAN PEREZ GOMEZ
FECHA DE NACIMIENTO: 01/02/1960 C.I: V-11.222.333 EDAD: 64 AÑOS
FECHA DE CONSULTA: 15/03/2024
REFERENCIA A CARDIOLOGIA
ENFERMEDAD ACTUAL: PACIENTE MASCULINO DE 64 AÑOS QUIEN REFIERE DOLOR.
EXAMEN FÍSICO: EXAMEN NEUROLOGICO SIN ALTERACIONES. GLASGOW 15/15.
IMPRESIÓN DIAGNÓSTICA: 1. Hipertensión arterial
2. Dislipidemia
PLAN: control en 30 días
ATENTAMENTE
DRA. MARIA LOPEZ RIVAS
MÉDICO INTERNISTA
CMT: 1.234 MPPS: 123456
"""

EXTERNAL_HEADER = """DRA. ANA TORRES MENDEZ
ESPECIALISTA EN CARDIOLOGÍA
MPPS: 98765 CM: 4321 RIF: V-12345678-9
INFORME MÉDICO CARDIOLÓGICO
NOMBRE DEL PACIENTE: PEDRO RAMOS DIAZ
C.I: 20.333.444 EDAD: 40
FECHA: 02-05-2023
DIAGNÓSTICO: Arritmia sinusal
TRATAMIENTO: reposo
"""

IMAGING = """CENTRO CLINICO DEMO
INFORME DE VIDEOCOLONOSCOPIA
PACIENTE: LUISA MARTINEZ
ESPECIALIDAD: GASTROENTEROLOGIA
MÉDICO SOLICITANTE: DR. CARLOS BLANCO SUAREZ
HALLAZGOS: mucosa normal
CONCLUSION: estudio normal
"""

OCR_NOISE = """INFORME MEDICO
PACIENTE: ROSA HERNANDEZ C.I: 9.876.543
DIAGNOSTICO: Gastritis
PLAN: dieta
OR. PABLO SANCHEZ VERA
MEDICO GASTROENTEROLOGO
M.P.P.S: 54.321
"""

BARE_STAMP = """INFORME MEDICO
PACIENTE: TOMAS GIL
DIAGNOSTICO: Lumbalgia
LUIS FERNANDO ACOSTA
MEDICO CIRUJANO ULA
TRAUMATOLOGO
MPPS: 77777
"""

CONTINUATION = """continua tratamiento indicado y control en 15 dias
DRA. MARIA LOPEZ RIVAS
MÉDICO INTERNISTA
MPPS: 123456
"""


class Doctors(unittest.TestCase):
    def test_gps_footer_stamp(self):
        parsed = parse_page(GPS_FOOTER)
        doctor = parsed["doctors"][0]
        self.assertEqual(doctor["name"], "Maria Lopez Rivas")
        self.assertEqual((doctor["title"], doctor["mpps"], doctor["colegio"]), ("dra", "123456", "1234"))
        self.assertEqual((doctor["zone"], doctor["role"], doctor["rule_id"]), ("footer", "firmante", "stamp_dr"))
        self.assertEqual(doctor["especialidad"], "medicina_interna")

    def test_gps_rif_is_not_the_doctor(self):
        doctor = parse_page(GPS_FOOTER)["doctors"][0]
        self.assertIsNone(doctor["rif"])

    def test_external_header(self):
        doctor = parse_page(EXTERNAL_HEADER)["doctors"][0]
        self.assertEqual((doctor["zone"], doctor["mpps"], doctor["rif"]), ("header", "98765", "V-123456789"))
        self.assertEqual(doctor["especialidad"], "cardiologia")

    def test_solicitante_label(self):
        doctors = parse_page(IMAGING)["doctors"]
        self.assertEqual([(d["role"], d["name"]) for d in doctors], [("solicitante", "Carlos Blanco Suarez")])

    def test_or_misread_needs_a_license(self):
        doctor = parse_page(OCR_NOISE)["doctors"][0]
        self.assertEqual((doctor["title"], doctor["name"], doctor["mpps"]), ("dr", "Pablo Sanchez Vera", "54321"))
        self.assertEqual(doctor["rule_id"], "stamp_or")
        self.assertEqual(parse_page("OR. JUAN PEREZ\nsin sello")["doctors"], [])

    def test_bare_name_stamp_with_degree(self):
        doctor = parse_page(BARE_STAMP)["doctors"][0]
        self.assertEqual((doctor["name"], doctor["rule_id"]), ("Luis Fernando Acosta", "stamp_bare_name"))
        self.assertEqual((doctor["degree"], doctor["degree_university"]), ("medico_cirujano", "ULA"))
        self.assertEqual(doctor["especialidad"], "traumatologia")


class Especialidad(unittest.TestCase):
    def test_referral_is_not_the_visit_specialty(self):
        terms = parse_page(GPS_FOOTER)["terms"]
        self.assertEqual(referred_specialty(terms), "cardiologia")
        self.assertEqual(visit_specialty(terms), ("medicina_interna", "doctor_title"))

    def test_neuro_exam_prose_is_ignored(self):
        terms = parse_page(GPS_FOOTER)["terms"]
        self.assertNotIn("neurologia", {t["especialidad"] for t in terms})

    def test_report_title_adjective(self):
        terms = parse_page(EXTERNAL_HEADER)["terms"]
        self.assertIn(("report_title", "cardiologia"), {(t["context"], t["especialidad"]) for t in terms})

    def test_label_wins_and_procedure_from_title(self):
        terms = parse_page(IMAGING)["terms"]
        self.assertEqual(visit_specialty(terms), ("gastroenterologia", "label"))
        self.assertEqual(page_procedure(terms), "colonoscopia")


class PatientAndDiagnosis(unittest.TestCase):
    def test_patient_block(self):
        patient = parse_page(GPS_FOOTER)["patient"]
        self.assertEqual((patient["name"], patient["ci"], patient["edad"]), ("Juan Perez Gomez", "11222333", 64))

    def test_patient_on_next_line_ci(self):
        patient = parse_page(EXTERNAL_HEADER)["patient"]
        self.assertEqual((patient["name"], patient["ci"]), ("Pedro Ramos Diaz", "20333444"))

    def test_prose_paciente_is_not_a_name(self):
        patient = parse_page("PACIENTE FEMENINO DE 30 AÑOS QUE CONSULTA")["patient"]
        self.assertIsNone(patient["name"])

    def test_encounter_date_skips_birth_date(self):
        self.assertEqual(parse_page(GPS_FOOTER)["encounter_date"], "2024-03-15")
        self.assertEqual(parse_page(EXTERNAL_HEADER)["encounter_date"], "2023-05-02")

    def test_diagnosis_block(self):
        self.assertEqual(parse_page(GPS_FOOTER)["diagnosis"], "1. Hipertensión arterial 2. Dislipidemia")
        self.assertEqual(parse_page(EXTERNAL_HEADER)["diagnosis"], "Arritmia sinusal")


class Grouping(unittest.TestCase):
    def test_continuation_page_joins_report(self):
        first = {"source_file_id": "f", "page_index": 1, "document_type": "informe_medico", "parsed": parse_page(OCR_NOISE)}
        second = {"source_file_id": "f", "page_index": 2, "document_type": "informe_medico", "parsed": parse_page(CONTINUATION)}
        other = {"source_file_id": "f", "page_index": 3, "document_type": "informe_medico", "parsed": parse_page(GPS_FOOTER)}
        groups = group_report_pages([first, second, other])
        self.assertEqual([len(g) for g in groups], [2, 1])

    def test_fingerprint_ignores_spacing(self):
        self.assertEqual(parse_page("INFORME  MEDICO\nX")["fingerprint"], parse_page("INFORME MEDICO X")["fingerprint"])


if __name__ == "__main__":
    unittest.main()
