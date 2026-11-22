"""Item parsing and duplicate detection. Fake rows only."""

from __future__ import annotations

import datetime as dt
import unittest

from workbook_enrichment.authorization_items import (
    items_or_service,
    parse_request_items,
    partition_copies,
    RequestCopy,
)
from workbook_enrichment.canonical import HEADER_ALIASES

CI = "11222333"
NAME = "JUAN PEREZ"


def _copy(**extra) -> RequestCopy:
    base = dict(
        line_id="line-a",
        person_id="person-1",
        source_file="SEGUROS VENEZUELA/AMP APS 4064.xls",
        source_row="ESTUDIOS ESPECIALES:17",
        source_hash="hash-a",
        service_date=dt.date(2025, 1, 28),
        amount_bs=16995,
        diagnosis="INFECCION RESPIRATORIA BAJA",
        labels=("RX DE TORAX", "PANEL RESPIRATORIO"),
        invoice_id=None,
        referenced=False,
    )
    base.update(extra)
    return RequestCopy(**base)


class AuthorizationItemTests(unittest.TestCase):
    def test_header_aliases_map_specialty_and_study(self) -> None:
        self.assertEqual(HEADER_ALIASES["ESPECIALIDAD MEDICA"], "service_description")
        self.assertEqual(HEADER_ALIASES["ESTUDIO ESPECIAL"], "service_description")

    def test_continuation_row_is_an_item(self) -> None:
        headers = ["NOMBRE DEL PACIENTE", "C.I. PACIENTE", "ESTUDIO ESPECIAL", ""]
        rows = [
            headers,
            [NAME, CI, "", None],
            ["", "", "HEMATOLOGIA COMPLETA", None],
            ["", "", "PANEL RESPIRATORIO", 250],
            ["OTRA PERSONA", "99888777", "OTRO ESTUDIO", None],
        ]
        items = parse_request_items(headers, rows, 1, "ESTUDIOS ESPECIALES")
        self.assertEqual([item.label for item in items], ["HEMATOLOGIA COMPLETA", "PANEL RESPIRATORIO"])
        self.assertEqual(items[0].kind, "estudio")
        self.assertIsNone(items[0].quantity)
        self.assertEqual(items[1].quantity, 250)
        self.assertEqual(items[1].reason, "continuation")

    def test_same_row_specialty_is_one_item(self) -> None:
        headers = ["NOMBRE DEL PACIENTE", "C.I. PACIENTE", "ESPECIALIDAD MEDICA", "MONTO"]
        rows = [headers, [NAME, CI, "CONSULTA GINECOLOGICA", 45]]
        items = parse_request_items(headers, rows, 1, "CONSULTA")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "CONSULTA GINECOLOGICA")
        self.assertEqual(items[0].kind, "consulta")
        self.assertIsNone(items[0].quantity)
        self.assertEqual(items[0].reason, "same_row")

    def test_service_description_without_study_rows_is_one_servicio(self) -> None:
        items = items_or_service([], "LABORATORIO", "11")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "servicio")
        self.assertEqual(items[0].label, "LABORATORIO")

    def test_identical_copies_collapse_to_one_header(self) -> None:
        numbered = _copy()
        plain = _copy(
            line_id="line-b",
            source_file="SEGUROS VENEZUELA/AMP APS.xls",
            source_row="ESTUDIOS ESPECIALES:17",
            source_hash="hash-b",
        )
        groups = partition_copies([numbered, plain])
        self.assertEqual(len(groups), 1)
        canonical, extras = groups[0]
        self.assertEqual(canonical.line_id, "line-a")
        self.assertEqual([extra.line_id for extra in extras], ["line-b"])

    def test_different_amount_stays_a_separate_request(self) -> None:
        numbered = _copy(amount_bs=849.75, labels=("HEMATOLOGIA COMPLETA",))
        other = _copy(
            line_id="line-b",
            source_file="SEGUROS VENEZUELA/AMP APS.xls",
            source_hash="hash-b",
            amount_bs=16995,
            labels=("HEMATOLOGIA COMPLETA",),
        )
        groups = partition_copies([numbered, other])
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(extras == [] for _, extras in groups))

    def test_two_numbered_files_stay_separate(self) -> None:
        first = _copy(source_file="SEGUROS VENEZUELA/AMP APS 4064.xls")
        second = _copy(
            line_id="line-b",
            source_file="SEGUROS VENEZUELA/AMP APS 4045.xls",
            source_hash="hash-b",
        )
        groups = partition_copies([first, second])
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(extras == [] for _, extras in groups))

    def test_empty_labels_do_not_collapse(self) -> None:
        numbered = _copy(labels=())
        plain = _copy(
            line_id="line-b",
            source_file="SEGUROS VENEZUELA/AMP APS.xls",
            source_hash="hash-b",
            labels=(),
        )
        groups = partition_copies([numbered, plain])
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(extras == [] for _, extras in groups))

    def test_referenced_copy_stays_visible(self) -> None:
        numbered = _copy()
        linked = _copy(
            line_id="line-b",
            source_file="SEGUROS VENEZUELA/AMP APS.xls",
            source_hash="hash-b",
            invoice_id="invoice-1",
        )
        groups = partition_copies([numbered, linked])
        hidden = [extra for _, extras in groups for extra in extras]
        self.assertEqual(hidden, [])
        self.assertEqual({line.line_id for line, _ in groups}, {"line-a", "line-b"})


if __name__ == "__main__":
    unittest.main()
