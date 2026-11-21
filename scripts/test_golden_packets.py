"""End-to-end golden packets (anonymized): classifier → segmenter → fiscal extract → role rules."""

from __future__ import annotations

import unittest

from document_types import classify_document
from fiscal_extract import extract
from invoice_pages import judge_page
from segment_scan_packets import Page, confidence, segment_folder
from upload_documents_to_blob import CI_TITULAR_TYPES

FISCAL = """G.P.S. GESTION PROFESIONAL DE SALUD AVILA, C.A.
RIF.: J-12345678-9
N° DE CONTROL 00 012345 FORMA LIBRE
SEGUROS EJEMPLO C.A. Factura N*00012345
Fecha de Emisión: 05/03/2025
Titular: JUAN PEREZ GOMEZ V-11222333
Paciente: LUIS PEREZ DIAZ
Tomador: ORDEN:7654321
CONSULTA PEDIATRIA (E) 1 1234567 1/01 1.500,00 0,00 1.500,00
TOTAL FACTURA: 1.500,00 40,00
"""

CLAIM_FORM = """SEGUROS EJEMPLO
DECLARACION DE SINIESTRO DE HCM
FACTURA N° 12345
NOMBRE DEL ASEGURADO JUAN PEREZ GOMEZ
BENEFICIARIO LUIS PEREZ DIAZ
"""

ACTA = """REPÚBLICA BOLIVARIANA DE VENEZUELA
CONSEJO NACIONAL ELECTORAL
REGISTRO CIVIL MUNICIPAL
Acta N° 08
LUIS ANDRES PEREZ DIAZ
JUAN JOSE PEREZ GOMEZ
titular de la Cedula de identidad N° V-11.222.333
"""

COLLAGE = """Gestión Profesional de Salud Ávila, C.A
pl a DOCUMENTOS DE
aa a En > IDENTIFICACION
PEREZ GOMEZ
Juan J. Perez A.
11.222.333
"""

INFORME = "INFORME MEDICO\nNOMBRE DEL PACIENTE: LUIS PEREZ DIAZ\nEDAD 6\nDIAGNOSTICO: OTITIS\n"


def classified(texts: list[str]) -> list[Page]:
    pages = []
    for i, text in enumerate(texts, start=1):
        dtype, _ = classify_document(text)
        pages.append(Page(f"LOTE/IMG_{i}.JPG", 1, text, dtype))
    return pages


class TitularWithMinorAndActaTests(unittest.TestCase):
    def setUp(self):
        self.pages = classified([FISCAL, CLAIM_FORM, ACTA, COLLAGE, INFORME])

    def test_page_types(self):
        self.assertEqual(
            [p.dtype for p in self.pages],
            ["factura_fiscal", "comprobante", "acta_nacimiento", "documentos_identificacion", "informe_medico"],
        )

    def test_one_confident_packet(self):
        packets, orphans = segment_folder("LOTE", self.pages)
        self.assertEqual((len(packets), orphans), (1, 0))
        self.assertEqual(packets[0].key, "12345")
        self.assertEqual(len(packets[0].pages), 5)
        self.assertGreaterEqual(confidence(packets[0]), 0.6)

    def test_fiscal_names_parent_titular_and_child_patient(self):
        f = extract(FISCAL)
        self.assertEqual((f.titular_name, f.titular_ci), ("JUAN PEREZ GOMEZ", "11222333"))
        self.assertEqual((f.patient_name, f.patient_ci), ("LUIS PEREZ DIAZ", None))

    def test_only_identity_pages_can_promote_a_ci(self):
        promoting = [p.dtype for p in self.pages if p.dtype in CI_TITULAR_TYPES]
        self.assertEqual(promoting, ["documentos_identificacion"])
        self.assertNotIn("acta_nacimiento", CI_TITULAR_TYPES)


INFORME_STAMPED = """G.P.S. GESTION PROFESIONAL DE SALUD RIF J-41029281-4
INFORME MÉDICO
PACIENTE: LUIS PEREZ DIAZ
FECHA DE NACIMIENTO: 01/02/2018 EDAD: 6 FECHA DE CONSULTA: 05/03/2025
EXAMEN FISICO: EXAMEN NEUROLOGICO NORMAL
DIAGNÓSTICO: Otitis media aguda
PLAN: antibiótico
DRA. ANA TORRES MENDEZ
MÉDICO PEDIATRA
CMT: 1.111 MPPS: 222222
"""


class InformeMedicoGoldenTests(unittest.TestCase):
    def test_informe_reads_doctor_specialty_patient_and_diagnosis(self):
        from clinical_parse import parse_page, visit_specialty

        self.assertEqual(classify_document(INFORME_STAMPED)[0], "informe_medico")
        parsed = parse_page(INFORME_STAMPED)
        doctor = parsed["doctors"][0]
        self.assertEqual((doctor["mpps"], doctor["especialidad"], doctor["role"]), ("222222", "pediatria", "firmante"))
        self.assertEqual(parsed["patient"]["name"], "Luis Perez Diaz")
        self.assertEqual(parsed["encounter_date"], "2025-03-05")
        self.assertEqual(parsed["diagnosis"], "Otitis media aguda")
        self.assertEqual(visit_specialty(parsed["terms"]), ("pediatria", "doctor_title"))

    def test_minimal_informe_has_no_doctor(self):
        from clinical_parse import parse_page

        parsed = parse_page(INFORME)
        self.assertEqual(parsed["doctors"], [])
        self.assertEqual(parsed["diagnosis"], "OTITIS")


class ClaimFormGoldenTests(unittest.TestCase):
    def test_claim_form_never_opens_a_packet(self):
        self.assertEqual(judge_page(CLAIM_FORM), ("attachment", "claim_form"))
        packets, orphans = segment_folder("LOTE", classified([CLAIM_FORM, INFORME]))
        self.assertEqual((packets, orphans), ([], 2))


if __name__ == "__main__":
    unittest.main()
