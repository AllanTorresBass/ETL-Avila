#!/usr/bin/env python3
"""Cut scanner image runs (rule ``scan_outside_invoice``) into invoice packets.

Within each folder, files are walked in natural name order (IMG_9 < IMG_10).
A fiscal sheet opens a packet; the pages after it join until the next fiscal
sheet with a different invoice number. A packet is valid when the fiscal
extractor reads an invoice number or a control number (the loader resolves a
control-only packet through ``avila.invoice.control_number``).

Confidence = 0.35 invoice or control number + 0.1 when both are read
           + 0.25 when page two is the claim form / carta aval (Miranda order)
           + 0.3 × share of attachment pages repeating a labeled patient/titular surname
           + 0.1 when the packet has 2–30 pages
           − 0.35 when it holds two claim forms (a fiscal sheet was probably missed).

Writes ``output/invoices/scan-packets.csv`` (git-ignored, no names). With
``--reviews`` low-confidence packets (< 0.6) become ``segment_review`` items.

  PYTHONPATH=scripts .venv/bin/python scripts/segment_scan_packets.py [--folder SUBSTR] [--reviews]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from document_types import classify_document  # noqa: E402
from fiscal_extract import FiscalFields, extract  # noqa: E402
from invoice_rules import fold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACKETS_CSV = ROOT / "output" / "invoices" / "scan-packets.csv"
LOW_CONFIDENCE = 0.6
PACKET_FIELDS = [
    "packet_id",
    "folder",
    "invoice_number",
    "control_number",
    "pages",
    "page_refs",
    "page_types",
    "consistency",
    "confidence",
]


@dataclass
class Page:
    path: str
    page: int
    text: str
    dtype: str


@dataclass
class Packet:
    folder: str
    pages: list[Page] = field(default_factory=list)
    fiscal: FiscalFields = field(default_factory=FiscalFields)

    @property
    def invoice_number(self) -> str | None:
        return self.fiscal.invoice_number

    @property
    def key(self) -> str | None:
        """Invoice number, else the control number (pre-printed forms often leave the number box unread)."""
        return self.fiscal.invoice_number or self.fiscal.control_number

    @property
    def packet_id(self) -> str:
        first = self.pages[0]
        return hashlib.sha256(f"{first.path}#{first.page}".encode()).hexdigest()[:16]


def natural_key(path: str) -> list:
    name = PurePosixPath(path).name
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", name)]


_LABELED_NAME = re.compile(
    r"(?:PACIENTE|TITULAR|BENEFICIARIO|ASEGURADO|APELLIDOS?\s+Y\s+NOMBRES?)\s*:?\s*([A-Z][A-Z ]{5,60})"
)
_NOT_NAME = {
    "NOMBRE", "NOMBRES", "APELLIDO", "APELLIDOS", "CEDULA", "IDENTIDAD", "EDAD", "FECHA",
    "TELEFONO", "DIRECCION", "SEXO", "POLIZA", "TITULAR", "PACIENTE", "BENEFICIARIO", "DATOS",
}
_CLAIM_PAGE = {"comprobante", "carta_aval"}


def packet_names(packet: Packet) -> set[str]:
    """Surname-like tokens from labeled name fields on any page plus the fiscal extract."""
    tokens: set[str] = set()
    for name in (packet.fiscal.titular_name, packet.fiscal.patient_name):
        tokens.update(fold(name or "").split())
    for page in packet.pages:
        for m in _LABELED_NAME.finditer(fold(page.text)):
            tokens.update(m.group(1).split())
    return {t for t in tokens if len(t) >= 4 and t not in _NOT_NAME}


def consistency(packet: Packet) -> float:
    names = packet_names(packet)
    others = [p for p in packet.pages if p.dtype != "factura_fiscal" and p.text.strip()]
    if not names or not others:
        return 0.0
    hits = sum(1 for p in others if names & set(re.findall(r"[A-Z]{4,}", fold(p.text))))
    return hits / len(others)


def confidence(packet: Packet) -> float:
    """0.35 key, +0.1 both numbers, +0.25 claim form second, +0.3 × name consistency, +0.1 size; −0.35 two claims."""
    score = 0.0
    if packet.key:
        score += 0.35
    if packet.invoice_number and packet.fiscal.control_number:
        score += 0.1
    types = [p.dtype for p in packet.pages]
    if len(types) > 1 and types[1] in _CLAIM_PAGE:
        score += 0.25
    score += 0.3 * consistency(packet)
    if 2 <= len(packet.pages) <= 30:
        score += 0.1
    if sum(1 for t in types if t == "comprobante") > 1:
        score -= 0.35
    return round(max(0.0, min(score, 1.0)), 3)


def segment_folder(folder: str, pages: list[Page]) -> tuple[list[Packet], int]:
    """Return (packets, leading_orphan_pages)."""
    packets: list[Packet] = []
    current: Packet | None = None
    orphans = 0
    for page in pages:
        if page.dtype == "factura_fiscal":
            fields = extract(page.text)
            same = current is not None and (
                (fields.invoice_number and fields.invoice_number == current.fiscal.invoice_number)
                or (fields.control_number and fields.control_number == current.fiscal.control_number)
            )
            if not same:
                current = Packet(folder)
                packets.append(current)
            current.pages.append(page)
            current.fiscal.merge(fields)
            continue
        if current is None:
            orphans += 1
            continue
        current.pages.append(page)
    return packets, orphans


def load_folder_pages(rows: list[dict]) -> dict[str, list[Page]]:
    from ocr_invoice_pages import _read_cache

    by_folder: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_folder[str(PurePosixPath(row["path"]).parent)].append(row)
    out: dict[str, list[Page]] = {}
    for folder, items in by_folder.items():
        pages: list[Page] = []
        for row in sorted(items, key=lambda r: natural_key(r["path"])):
            cache = _read_cache(row["path"])
            if not cache:
                continue
            for i, rec in enumerate(cache.get("pages") or [], start=1):
                text = rec.get("text") or ""
                dtype, _ = classify_document(text, page_error=rec.get("error") or "")
                pages.append(Page(row["path"], i, text, dtype))
        if pages:
            out[folder] = pages
    return out


def main() -> int:
    from ocr_invoice_pages import _load_targets

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--folder", default="")
    parser.add_argument("--reviews", action="store_true", help="Open segment_review items in Neon")
    args = parser.parse_args()
    rows = _load_targets("scan", folder=args.folder)
    folders = load_folder_pages(rows)
    stats: Counter = Counter()
    packets: list[Packet] = []
    for folder, pages in folders.items():
        found, orphans = segment_folder(folder, pages)
        stats["folders"] += 1
        stats["pages"] += len(pages)
        stats["leading_orphan_pages"] += orphans
        packets.extend(found)
    PACKETS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PACKETS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PACKET_FIELDS)
        writer.writeheader()
        for packet in packets:
            conf = confidence(packet)
            stats["packets"] += 1
            if packet.invoice_number:
                stats["key:invoice_number"] += 1
            elif packet.key:
                stats["key:control_only"] += 1
            else:
                stats["key:none"] += 1
            stats["high_confidence" if conf >= LOW_CONFIDENCE else "low_confidence"] += 1
            writer.writerow(
                {
                    "packet_id": packet.packet_id,
                    "folder": packet.folder,
                    "invoice_number": packet.invoice_number or "",
                    "control_number": packet.fiscal.control_number or "",
                    "pages": len(packet.pages),
                    "page_refs": "|".join(f"{p.path}#{p.page}" for p in packet.pages),
                    "page_types": "|".join(p.dtype for p in packet.pages),
                    "consistency": f"{consistency(packet):.2f}",
                    "confidence": conf,
                }
            )
    if args.reviews:
        _open_reviews(packets, stats)
    print(dict(stats))
    print("Wrote", PACKETS_CSV)
    return 0


def _open_reviews(packets: list[Packet], stats: Counter) -> None:
    import psycopg
    from psycopg.rows import dict_row

    import provenance
    from env_load import load_env

    env = load_env()
    url = env.get("DATABASE_URL_UNPOOLED") or env["DATABASE_URL"]
    provenance.start_run(url, "segment_scan_packets", {"reviews": True}, apply=True)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT invoice_number, id FROM avila.invoice")
        invoice_ids = {r["invoice_number"]: r["id"] for r in cur.fetchall()}
        with conn.pipeline():
            _queue_reviews(cur, packets, invoice_ids, stats)
        conn.commit()
    provenance.finish_run(url, dict(stats))


def _queue_reviews(cur, packets: list[Packet], invoice_ids: dict, stats: Counter) -> None:
    import provenance

    for packet in packets:
        conf = confidence(packet)
        if conf >= LOW_CONFIDENCE:
            continue
        provenance.open_review(
            cur,
            kind="segment_review",
            dedupe_key=f"segment_review:{packet.packet_id}",
            invoice_id=invoice_ids.get(packet.invoice_number or ""),
            evidence={
                "packet_id": packet.packet_id,
                "folder": packet.folder,
                "first_page": f"{packet.pages[0].path}#{packet.pages[0].page}",
                "pages": len(packet.pages),
                "invoice_number": packet.invoice_number,
                "page_types": [p.dtype for p in packet.pages][:30],
            },
            score=conf,
        )
        stats["segment_review_opened"] += 1


if __name__ == "__main__":
    raise SystemExit(main())
