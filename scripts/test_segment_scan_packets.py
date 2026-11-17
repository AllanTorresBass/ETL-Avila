"""Scanner packet segmentation on anonymized page runs."""

from __future__ import annotations

import unittest

from segment_scan_packets import Page, confidence, natural_key, segment_folder

FISCAL_A = "N° DE CONTROL 00 012345 FORMA LIBRE\nFactura N*00012345\nTitular: JUAN PEREZ GOMEZ V-11222333\n"
FISCAL_B = "N° DE CONTROL 00 012399 FORMA LIBRE\nFactura N*00012399\nTitular: MARIA LOPEZ DIAZ V-44555666\n"


def page(i, dtype, text="", path=None):
    return Page(path or f"LOTE/IMG_{i}.JPG", 1, text, dtype)


class SegmentTests(unittest.TestCase):
    def test_natural_order(self):
        paths = ["LOTE/IMG_10.JPG", "LOTE/IMG_9.JPG", "LOTE/IMG_100.JPG"]
        self.assertEqual(sorted(paths, key=natural_key), ["LOTE/IMG_9.JPG", "LOTE/IMG_10.JPG", "LOTE/IMG_100.JPG"])

    def test_fiscal_opens_packets_and_attachments_follow(self):
        pages = [
            page(1, "informe_medico", "INFORME"),
            page(2, "factura_fiscal", FISCAL_A),
            page(3, "cedula_identidad", "CEDULA PEREZ"),
            page(4, "informe_medico", "PACIENTE PEREZ"),
            page(5, "factura_fiscal", FISCAL_B),
            page(6, "carta_aval", "LOPEZ"),
        ]
        packets, orphans = segment_folder("LOTE", pages)
        self.assertEqual(orphans, 1)
        self.assertEqual([p.invoice_number for p in packets], ["12345", "12399"])
        self.assertEqual([len(p.pages) for p in packets], [3, 2])

    def test_copy_of_same_fiscal_sheet_stays_in_packet(self):
        pages = [page(1, "factura_fiscal", FISCAL_A), page(2, "factura_fiscal", FISCAL_A), page(3, "egreso", "PEREZ")]
        packets, _ = segment_folder("LOTE", pages)
        self.assertEqual(len(packets), 1)
        self.assertEqual(len(packets[0].pages), 3)

    def test_confidence_rewards_name_consistency(self):
        good, _ = segment_folder("L", [page(1, "factura_fiscal", FISCAL_A), page(2, "informe_medico", "PEREZ GOMEZ")])
        bad, _ = segment_folder("L", [page(1, "factura_fiscal", FISCAL_A), page(2, "informe_medico", "RODRIGUEZ")])
        self.assertGreaterEqual(confidence(good[0]), 0.6)
        self.assertLess(confidence(bad[0]), 0.6)

    def test_claim_form_second_raises_confidence(self):
        pages = [page(1, "factura_fiscal", FISCAL_A), page(2, "comprobante", "DECLARACION"), page(3, "otro_anexo", "X")]
        packets, _ = segment_folder("L", pages)
        self.assertGreaterEqual(confidence(packets[0]), 0.6)

    def test_two_claim_forms_penalized(self):
        pages = [page(1, "factura_fiscal", FISCAL_A), page(2, "comprobante", "A"), page(3, "comprobante", "B")]
        packets, _ = segment_folder("L", pages)
        self.assertLess(confidence(packets[0]), 0.6)

    def test_control_only_packet_has_key(self):
        packets, _ = segment_folder("L", [page(1, "factura_fiscal", "N* DE CONTROL 00 — 009773 FORMA LIBRE")])
        self.assertEqual(packets[0].key, "00-009773")

    def test_unreadable_fiscal_number_is_invalid(self):
        packets, _ = segment_folder("L", [page(1, "factura_fiscal", "FORMA LIBRE ilegible")])
        self.assertIsNone(packets[0].invoice_number)
        self.assertLess(confidence(packets[0]), 0.6)


class ResolvePacketInvoiceTests(unittest.TestCase):
    def _cur(self, one=None, many=()):
        from unittest.mock import MagicMock

        cur = MagicMock()
        cur.fetchone.return_value = one
        cur.fetchall.return_value = list(many)
        return cur

    def test_number_wins(self):
        from upload_documents_to_blob import _resolve_packet_invoice

        cur = self._cur(one={"control_number": "00-009773"})
        self.assertEqual(
            _resolve_packet_invoice(cur, {"invoice_number": "12345", "control_number": "00-009773"}),
            ("12345", "invoice_number"),
        )

    def test_number_with_conflicting_control_refused(self):
        from upload_documents_to_blob import _resolve_packet_invoice

        cur = self._cur(one={"control_number": "00-000001"})
        self.assertEqual(
            _resolve_packet_invoice(cur, {"invoice_number": "12345", "control_number": "00-009773"}),
            (None, "control_mismatch"),
        )

    def test_control_only_resolves_unique(self):
        from upload_documents_to_blob import _resolve_packet_invoice

        cur = self._cur(many=[{"invoice_number": "12345", "control_number": "00-9773"}])
        self.assertEqual(
            _resolve_packet_invoice(cur, {"invoice_number": "", "control_number": "00-009773"}),
            ("12345", "control_number"),
        )

    def test_control_unknown(self):
        from upload_documents_to_blob import _resolve_packet_invoice

        self.assertEqual(
            _resolve_packet_invoice(self._cur(), {"invoice_number": "", "control_number": "00-009773"}),
            (None, "control_unknown"),
        )


if __name__ == "__main__":
    unittest.main()
