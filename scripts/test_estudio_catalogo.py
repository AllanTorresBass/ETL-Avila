"""Clinic catalog: a study, and a specification under it when the page names one."""

import unittest

from estudio_catalogo import normalize_study


class NormalizeStudy(unittest.TestCase):
    def test_lab_panel_is_a_specification_of_the_service(self):
        self.assertEqual(
            normalize_study("laboratorio", "Exámenes de laboratorio"),
            ("laboratorio", "Exámenes de laboratorio", None),
        )
        self.assertEqual(
            normalize_study("laboratorio", "Hematología completa"),
            ("laboratorio", "Exámenes de laboratorio", "Hematología completa"),
        )

    def test_site_noise_does_not_invent_a_lab_type(self):
        self.assertEqual(
            normalize_study("laboratorio", "Insulina venosa"),
            ("laboratorio", "Exámenes de laboratorio", "Insulina"),
        )
        self.assertEqual(
            normalize_study("laboratorio", "Creatinina · Orina"),
            ("laboratorio", "Exámenes de laboratorio", "Creatinina"),
        )
        self.assertEqual(
            normalize_study("laboratorio", "Trigliceridos"),
            ("laboratorio", "Exámenes de laboratorio", "Triglicéridos"),
        )
        self.assertEqual(
            normalize_study("laboratorio", "Orina completa"),
            ("laboratorio", "Exámenes de laboratorio", "Orina completa"),
        )

    def test_imaging_specification_keeps_one_region(self):
        self.assertEqual(
            normalize_study("ecografia", "Ecografía"),
            ("ecografia", "Ecografía", None),
        )
        self.assertEqual(
            normalize_study("ecografia", "Ecografía abdominal"),
            ("ecografia", "Ecografía", "Ecografía abdominal"),
        )
        self.assertEqual(
            normalize_study("ecografia", "Ecografía abdominal pélvica renal"),
            ("ecografia", "Ecografía", "Ecografía abdominal pélvica"),
        )
        self.assertEqual(
            normalize_study("rayos_x", "Rayos X de tórax"),
            ("rayos_x", "Rayos X", "Rayos X de tórax"),
        )
        self.assertEqual(
            normalize_study("rayos_x", "Rayos X lumbar"),
            ("rayos_x", "Rayos X", "Rayos X de columna lumbar"),
        )

    def test_aliases_join_the_same_study(self):
        self.assertEqual(
            normalize_study("endoscopia", "Videogastroscopia"),
            ("endoscopia", "Endoscopia digestiva superior", "Videogastroscopia"),
        )
        self.assertEqual(
            normalize_study("corazon", "Cateterismo"),
            ("corazon", "Coronariografía", None),
        )
        self.assertEqual(
            normalize_study("corazon", "MAPA arterial"),
            ("corazon", "MAPA", "MAPA arterial"),
        )
        self.assertEqual(
            normalize_study("tomografia", "Urotomografía simple"),
            ("tomografia", "Tomografía", "Tomografía urológica"),
        )
        self.assertEqual(normalize_study("densitometria", "Densitometria"), ("densitometria", "Densitometría", None))
        self.assertEqual(
            normalize_study("funcional", "Flujometria urinaria"),
            ("funcional", "Flujometría", "Flujometría urinaria"),
        )

    def test_unmanaged_names_stay_out(self):
        self.assertIsNone(normalize_study(None, "Estudio"))
        self.assertIsNone(normalize_study(None, "Imagenología"))

    def test_ana_without_a_family_is_a_lab_specification(self):
        self.assertEqual(normalize_study(None, "ANA"), ("laboratorio", "Exámenes de laboratorio", "ANA"))
        self.assertEqual(normalize_study(None, "ANA de mano"), ("laboratorio", "Exámenes de laboratorio", "ANA"))


if __name__ == "__main__":
    unittest.main()
