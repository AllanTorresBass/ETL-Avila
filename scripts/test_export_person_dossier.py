"""Unit tests for export_person_dossier helpers (no Neon)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from export_person_dossier import (
    completeness_score,
    export_dossier,
    render_readme,
    resolve_person,
)


FAKE_CI = "11222333"
FAKE_NAME = "JUAN PEREZ"


class CompletenessScoreTests(unittest.TestCase):
    def test_high_score_when_fields_present(self):
        person = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "full_name": FAKE_NAME,
            "identity_number": FAKE_CI,
            "birth_date": "1990-01-01",
            "phone": "04141234567",
            "address": "Valera",
            "notes": "",
        }
        invoices = [{"role": "titular", "invoice_number": "99999"}]
        roles = [
            {"role": "titular", "full_name": FAKE_NAME, "identity_number": FAKE_CI},
            {
                "role": "beneficiario",
                "full_name": "PEDRO PEREZ",
                "identity_number": "99887766",
                "parentesco": "hijo",
            },
        ]
        docs = [
            {
                "document_type": "documentos_identificacion",
                "person_id": person["id"],
            },
            {"document_type": "factura_fiscal", "person_id": None},
        ]
        auth = [{"id": "1"}]
        reviews = []
        workbook = [{"workbook": "x.xlsx"}]
        score, gaps, parts = completeness_score(
            person, invoices, roles, docs, auth, reviews, workbook
        )
        self.assertGreaterEqual(score, 80)
        self.assertEqual(parts["reviews"], 5)
        self.assertFalse(any("missing CI" in g for g in gaps))

    def test_blocking_review_zeroes_review_points(self):
        person = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "full_name": FAKE_NAME,
            "identity_number": FAKE_CI,
            "birth_date": None,
            "phone": None,
            "address": None,
            "notes": None,
        }
        score, gaps, parts = completeness_score(
            person,
            [],
            [],
            [],
            [],
            [{"status": "open", "kind": "ci_conflict"}],
            [],
        )
        self.assertEqual(parts["reviews"], 0)
        self.assertTrue(any("ci_conflict" in g for g in gaps))
        self.assertLess(score, 40)


class ResolvePersonTests(unittest.TestCase):
    def test_resolve_by_ci(self):
        cur = MagicMock()
        cur.fetchone.return_value = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "full_name": FAKE_NAME,
            "identity_type": "cedula",
            "identity_number": FAKE_CI,
            "birth_date": None,
            "phone": None,
            "address": None,
            "notes": None,
        }
        row = resolve_person(cur, person_id=None, ci=f"V-{FAKE_CI}", name=None)
        self.assertEqual(row["identity_number"], FAKE_CI)
        cur.execute.assert_called()
        args = cur.execute.call_args[0]
        self.assertEqual(args[1], (FAKE_CI,))


class ExportDossierIntegrationTests(unittest.TestCase):
    def test_writes_artifacts_with_mocked_neon(self):
        person = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "full_name": FAKE_NAME,
            "identity_type": "cedula",
            "identity_number": FAKE_CI,
            "birth_date": "1990-01-01",
            "phone": "04141234567",
            "address": None,
            "notes": "fixture",
        }
        invoices = [
            {
                "invoice_number": "99999",
                "control_number": "00-1",
                "issue_date": "2026-01-01",
                "total_bs": 1,
                "total_usd": 1,
                "clave": "911",
                "account": "seguros_miranda",
                "role": "titular",
                "parentesco": None,
                "source": "fiscal_ocr",
                "year": 2026,
                "month": "ENERO",
                "lote": 1,
                "channel": "TEST",
                "invoice_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            }
        ]
        roles = [
            {
                "invoice_number": "99999",
                "full_name": FAKE_NAME,
                "identity_number": FAKE_CI,
                "role": "titular",
                "parentesco": None,
                "source": "fiscal_ocr",
            }
        ]
        docs = [
            {
                "invoice_number": "99999",
                "document_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "page_index": 1,
                "document_type": "factura_fiscal",
                "evidence": "heading",
                "upload_status": "uploaded",
                "blob_pathname": "x",
                "person_id": None,
                "sha256": "abc",
                "backup_path": "FACTURAS/FACT 99999.pdf",
                "file_label": "invoice_packet",
                "rule_id": "named_fact",
                "source_pages": 1,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            with patch("export_person_dossier.database_url", return_value="postgresql://x"), patch(
                "export_person_dossier.psycopg.connect"
            ) as connect, patch(
                "export_person_dossier._read_cache", return_value=None
            ), patch(
                "export_person_dossier.scan_workbook_rows", return_value=[]
            ):
                conn = MagicMock()
                cur = MagicMock()
                connect.return_value.__enter__.return_value = conn
                conn.cursor.return_value.__enter__.return_value = cur
                # resolve_person then each fetch_* uses same cursor sequentially
                cur.fetchone.return_value = person
                cur.fetchall.side_effect = [
                    invoices,  # fetch_invoices
                    roles,  # fetch_role_graph
                    docs,  # fetch_documents
                    [],  # fetch_auth_lines
                    [],  # fetch_reviews
                    [],  # fetch_provenance
                ]
                meta = export_dossier(
                    ci=FAKE_CI,
                    copy_pages=False,
                    workbook=False,
                    out_root=out_root,
                )

            dossier = out_root / FAKE_NAME
            self.assertTrue((dossier / "README.md").is_file())
            self.assertTrue((dossier / "neon-person.csv").is_file())
            self.assertTrue((dossier / "completeness.json").is_file())
            self.assertEqual(meta["identity_number"], FAKE_CI)
            self.assertIn("dossier", meta)
            readme = (dossier / "README.md").read_text(encoding="utf-8")
            self.assertIn(FAKE_NAME, readme)
            self.assertIn("Completeness", readme)
            payload = json.loads((dossier / "completeness.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["identity_number"], FAKE_CI)


class ReadmeTests(unittest.TestCase):
    def test_readme_mentions_score(self):
        person = {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "full_name": FAKE_NAME,
            "identity_number": FAKE_CI,
            "identity_type": "cedula",
            "birth_date": None,
            "phone": None,
            "address": None,
            "notes": None,
        }
        text = render_readme(
            person,
            [],
            [],
            [],
            [],
            [],
            [],
            12,
            ["missing DOB"],
            {"identity": 12, "graph": 0, "packets": 0, "workbook_auth": 0, "reviews": 5},
        )
        self.assertIn("12/100", text)
        self.assertIn("missing DOB", text)


if __name__ == "__main__":
    unittest.main()
