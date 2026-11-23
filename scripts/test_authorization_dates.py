import datetime as dt
import unittest

from repair_authorization_dates import plan_line
from workbook_enrichment.authorization_dates import (
    date_columns,
    month_from_text,
    period_from_saved,
    period_from_text,
    real_date,
)


class FakeBook:
    def __init__(self, headers, values, saved=None):
        self._headers, self._values, self.saved = headers, values, saved

    def row(self, sheet, excel_row):
        return self._headers, self._values


def line(**overrides):
    base = {
        "source_file": "PREVISORA/RELACION OCTUBRE LOTE I.xlsx",
        "source_row": "S. LA PREVISORA:5",
        "request_date": None,
        "service_date": None,
    }
    base.update(overrides)
    return base


class AuthorizationDateTests(unittest.TestCase):
    def test_real_date_rejects_excel_blank(self):
        self.assertIsNone(real_date(1.0))
        self.assertIsNone(real_date(dt.date(1899, 12, 31)))
        self.assertEqual(real_date("15/03/2025"), dt.date(2025, 3, 15))

    def test_period_needs_four_digit_year(self):
        self.assertEqual(period_from_text("SABANAS SEGURO MIRANDA MARZO LOTE 13 2025.xlsx"), dt.date(2025, 3, 1))
        self.assertEqual(period_from_text("S.M. ENERO LOTE 2 ,2025"), dt.date(2025, 1, 1))
        self.assertIsNone(period_from_text("MAYO 11 GPS"))
        self.assertIsNone(period_from_text("RELACION OCTUBRE LOTE I.xlsx"))

    def test_month_only_takes_year_from_save_date(self):
        self.assertEqual(month_from_text("RELACION DICIEMBRE LOTE I.xlsx"), 12)
        self.assertEqual(period_from_saved(12, dt.date(2024, 3, 4)), dt.date(2023, 12, 1))
        self.assertEqual(period_from_saved(1, dt.date(2024, 3, 4)), dt.date(2024, 1, 1))
        self.assertIsNone(period_from_saved(3, dt.date(2024, 11, 1)))

    def test_extra_header_maps(self):
        self.assertEqual(date_columns(["NOMBRE", "FECHA DE AUTORIZACION", "FECHA DE NACIMIENTO"]), {"request_date": 1})

    def test_plan_clears_counter_cell_and_keeps_period(self):
        book = FakeBook(["FECHA DE LA CITA", "TITULAR"], [12.0, "X"], saved=dt.date(2023, 10, 24))
        plan = plan_line(line(service_date=dt.date(1900, 1, 11)), book)
        self.assertIsNone(plan["service_date"])
        self.assertEqual(plan["cleared"], ["service_date"])
        self.assertEqual(plan["date_source"], "period")

    def test_plan_clears_sentinel_without_period(self):
        book = FakeBook(["FECHA DE ATENCION"], [12.0], saved=None)
        plan = plan_line(line(source_file="SEGUROS VENEZUELA/CITAS.xlsx", service_date=dt.date(1900, 1, 11)), book)
        self.assertIsNone(plan["service_date"])
        self.assertIsNone(plan["date_source"])

    def test_plan_keeps_real_date(self):
        book = FakeBook(["FECHA RECIBIDO"], [None], saved=dt.date(2023, 10, 24))
        plan = plan_line(line(request_date=dt.date(2023, 10, 3)), book)
        self.assertEqual(plan["request_date"], dt.date(2023, 10, 3))
        self.assertEqual(plan["date_source"], "request")

    def test_plan_period_only(self):
        book = FakeBook(["FECHA RECIBIDO"], [None], saved=dt.date(2023, 10, 24))
        plan = plan_line(line(), book)
        self.assertEqual(plan["date_source"], "period")
        self.assertEqual(plan["period_month"], dt.date(2023, 10, 1))


if __name__ == "__main__":
    unittest.main()
