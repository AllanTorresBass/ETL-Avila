"""OCR invoice packets and FACT-range scans. Writes invoice-pages.csv.

Only files already labeled invoice_packet or needs_page_check are opened.
OCR text is cached under output/invoices/ocr so a later run can re-judge
pages without rendering them again. The CSV evidence column names matched
tokens and does not copy page text.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from posixpath import basename, dirname, join, normpath

sys.path.insert(0, str(Path(__file__).resolve().parent))

from invoice_pages import judge_page

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "Avila-backup"
OUT_DIR = ROOT / "output" / "invoices"
CACHE_DIR = OUT_DIR / "ocr"
INVENTORY = OUT_DIR / "invoices.csv"
PAGE_CSV = OUT_DIR / "invoice-pages.csv"

PAGE_FIELDS = [
    "path",
    "page",
    "pages",
    "file_label",
    "invoice_number",
    "invoice_range",
    "page_label",
    "is_fiscal_invoice",
    "evidence",
    "duplicate_group",
]

TARGET_LABELS = {"invoice_packet", "needs_page_check"}
SCAN_RULE = "scan_outside_invoice"
SCAN_PAGE_CSV = OUT_DIR / "scan-pages.csv"


def cache_path(relative: str) -> Path:
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _child_env() -> dict:
    env = os.environ.copy()
    env["OMP_THREAD_LIMIT"] = "1"
    return env


def _tesseract(image: Path) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", "spa", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=_child_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", f"tesseract_failed:{type(exc).__name__}"
    if proc.returncode != 0 and not proc.stdout.strip():
        err = (proc.stderr or "").strip().splitlines()
        detail = err[-1][:180] if err else f"exit_{proc.returncode}"
        return "", f"unreadable:{detail}"
    return proc.stdout, ""


def _render_pdf(pdf: Path, dest: Path) -> tuple[list[Path], str]:
    try:
        proc = subprocess.run(
            ["pdftoppm", "-png", "-r", "120", "-gray", str(pdf), str(dest / "page")],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=_child_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"render_failed:{type(exc).__name__}"
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        detail = err[-1][:180] if err else f"exit_{proc.returncode}"
        return [], f"render_failed:{detail}"
    pages = sorted(dest.glob("page*.png"))
    return pages, ""


_PML = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_RASTER = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def _render_office(source: Path, dest: Path) -> tuple[list[Path | None], str]:
    """Extract one raster image per slide, in slide order.

    Invoice packets stored as PowerPoint are photo slides. The page is the
    largest picture on that slide; a small logo is ignored. Binary .ppt is
    not OOXML and is left unsupported.
    """
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        return [], f"render_failed:{type(exc).__name__}"
    with archive:
        names = set(archive.namelist())
        if "ppt/presentation.xml" not in names or "ppt/_rels/presentation.xml.rels" not in names:
            return [], "unsupported:office_layout"
        try:
            presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
            deck_rels = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        except ET.ParseError:
            return [], "render_failed:ParseError"
        rel_target = {
            rel.attrib["Id"]: rel.attrib.get("Target", "")
            for rel in deck_rels
            if rel.attrib.get("Id")
        }
        slides: list[str] = []
        for slide_id in presentation.iter(f"{_PML}sldId"):
            target = rel_target.get(slide_id.attrib.get(f"{_OFFICE_REL}id", ""), "")
            if not target:
                continue
            slide_path = target.lstrip("/")
            if not slide_path.startswith("ppt/"):
                slide_path = normpath(join("ppt", slide_path))
            slides.append(slide_path)
        if not slides:
            return [], "no_pages"
        images: list[Path | None] = []
        for index, slide_path in enumerate(slides, start=1):
            rel_path = normpath(join(dirname(slide_path), "_rels", basename(slide_path) + ".rels"))
            chosen = _largest_slide_image(archive, names, slide_path, rel_path)
            if chosen is None:
                images.append(None)
                continue
            suffix = Path(chosen).suffix.lower()
            out = dest / f"page-{index:02d}{suffix}"
            out.write_bytes(archive.read(chosen))
            images.append(out)
    return images, ""


def _largest_slide_image(
    archive: zipfile.ZipFile, names: set[str], slide_path: str, rel_path: str
) -> str | None:
    if rel_path not in names:
        return None
    try:
        rels = ET.fromstring(archive.read(rel_path))
    except ET.ParseError:
        return None
    best_name = None
    best_size = -1
    for rel in rels:
        if not rel.attrib.get("Type", "").endswith("/image"):
            continue
        target = rel.attrib.get("Target") or ""
        media = normpath(join(dirname(slide_path), target)).lstrip("/")
        if media not in names:
            continue
        suffix = Path(media).suffix.lower()
        if suffix not in _RASTER:
            continue
        size = archive.getinfo(media).file_size
        if size > best_size:
            best_size = size
            best_name = media
    return best_name


def ocr_file(relative: str) -> dict:
    """OCR one backup-relative file. Safe to call in a worker process."""
    source = BACKUP / relative
    record = {"path": relative, "error": "", "pages": []}
    if not source.is_file():
        record["error"] = "missing"
        return record
    suffix = source.suffix.lower()
    with tempfile.TemporaryDirectory(prefix="avila-ocr-") as tmp:
        folder = Path(tmp)
        images: list[Path] = []
        if suffix == ".pdf":
            images, error = _render_pdf(source, folder)
            if error:
                record["error"] = error
                record["pages"].append({"page": 1, "text": "", "error": error})
                return record
        elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            images = [source]
        elif suffix in {".pptx", ".potx"}:
            images, error = _render_office(source, folder)
            if error and not images:
                record["error"] = error
                record["pages"].append({"page": 1, "text": "", "error": error})
                return record
        else:
            record["error"] = f"unsupported:{suffix or 'none'}"
            record["pages"].append({"page": 1, "text": "", "error": record["error"]})
            return record
        if not images:
            record["error"] = "no_pages"
            record["pages"].append({"page": 1, "text": "", "error": "no_pages"})
            return record
        for index, image in enumerate(images, start=1):
            if image is None:
                record["pages"].append({"page": index, "text": "", "error": "no_slide_image"})
                continue
            text, error = _tesseract(image)
            record["pages"].append({"page": index, "text": text, "error": error})
    return record


def _load_targets(
    scope: str = "invoice",
    *,
    folder: str = "",
    year: str = "",
    month: str = "",
) -> list[dict]:
    """Inventory rows for one OCR scope.

    ``invoice``: packets and FACT-range scans. ``scan``: scanner images outside
    any FACT folder (rule ``scan_outside_invoice``), one per duplicate group,
    sorted by path so a packet's pages stay contiguous in the cache walk.
    """
    rows = []
    seen_groups: set[str] = set()
    needle = folder.casefold()
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if scope == "invoice":
                if row["label"] in TARGET_LABELS:
                    rows.append(row)
                continue
            if row["rule_id"] != SCAN_RULE:
                continue
            if needle and needle not in row["path"].casefold():
                continue
            if year and row.get("year") != year:
                continue
            if month and (row.get("month") or "").casefold() != month.casefold():
                continue
            group = row.get("duplicate_group") or ""
            if group:
                if group in seen_groups:
                    continue
                seen_groups.add(group)
            rows.append(row)
    if scope == "scan":
        rows.sort(key=lambda r: r["path"])
    return rows


def _write_cache(relative: str, record: dict) -> None:
    target = cache_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)


def _read_cache(relative: str) -> dict | None:
    target = cache_path(relative)
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def rows_from_record(file_row: dict, record: dict) -> list[dict]:
    pages = record.get("pages") or []
    total = len(pages)
    out = []
    for page in pages:
        text = page.get("text") or ""
        error = page.get("error") or ""
        if error or not text.strip():
            label, evidence = "unreadable", error or "empty_ocr"
        else:
            label, evidence = judge_page(text)
        out.append({
            "path": file_row["path"],
            "page": page.get("page", ""),
            "pages": total,
            "file_label": file_row["label"],
            "invoice_number": file_row.get("invoice_number", ""),
            "invoice_range": file_row.get("invoice_range", ""),
            "page_label": label,
            "is_fiscal_invoice": "yes" if label == "fiscal_invoice" else "no",
            "evidence": evidence,
            "duplicate_group": file_row.get("duplicate_group", ""),
        })
    return out


def write_page_csv(file_rows: list[dict], out: Path = PAGE_CSV) -> None:
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAGE_FIELDS)
        writer.writeheader()
        for file_row in file_rows:
            record = _read_cache(file_row["path"])
            if record is None:
                continue
            writer.writerows(rows_from_record(file_row, record))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OCR invoice packets and candidate scans")
    parser.add_argument("--limit", type=int, default=0, help="OCR at most this many files that are not cached yet")
    parser.add_argument(
        "--scope",
        choices=("invoice", "scan"),
        default="invoice",
        help="invoice: packets + FACT-range scans; scan: scanner files outside FACT folders",
    )
    parser.add_argument("--folder", default="", help="scan scope: path substring filter")
    parser.add_argument("--year", default="", help="scan scope: inventory year (e.g. 2025)")
    parser.add_argument("--month", default="", help="scan scope: inventory month name")
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    if not INVENTORY.is_file():
        sys.exit(f"Missing inventory: {INVENTORY}")
    targets = _load_targets(args.scope, folder=args.folder, year=args.year, month=args.month)
    uncached = [row["path"] for row in targets if not cache_path(row["path"]).is_file()]
    pending = uncached[: args.limit] if args.limit else uncached
    print(f"Targets {len(targets):,}; uncached {len(uncached):,}; this run {len(pending):,}")
    workers = args.workers or min(8, os.cpu_count() or 4)
    done = 0
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(ocr_file, relative): relative for relative in pending}
            for future in as_completed(futures):
                relative = futures[future]
                try:
                    record = future.result()
                except Exception as exc:  # noqa: BLE001 — keep the walk going
                    record = {
                        "path": relative,
                        "error": f"worker:{type(exc).__name__}",
                        "pages": [{"page": 1, "text": "", "error": f"worker:{type(exc).__name__}"}],
                    }
                _write_cache(relative, record)
                done += 1
                if done % 100 == 0 or done == len(pending):
                    print(f"OCR {done:,}/{len(pending):,}", flush=True)
    if args.scope == "scan":
        if not (args.folder or args.year or args.month):
            write_page_csv(targets, SCAN_PAGE_CSV)
            print("Wrote", SCAN_PAGE_CSV)
        return
    write_page_csv(targets)
    fiscal = attachment = unreadable = 0
    with PAGE_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["page_label"] == "fiscal_invoice":
                fiscal += 1
            elif row["page_label"] == "unreadable":
                unreadable += 1
            else:
                attachment += 1
    print(f"Pages fiscal={fiscal:,} attachment={attachment:,} unreadable={unreadable:,}")
    print("Wrote", PAGE_CSV)
    _write_page_summary(fiscal, attachment, unreadable)


def _write_page_summary(fiscal: int, attachment: int, unreadable: int) -> None:
    """Append page-pass counts to the inventory summary. Counts only, no paths."""
    section = f"""
## Page pass

OCR (Spanish Tesseract, 120 DPI) ran on invoice packets and on scans whose folder title contains a `FACT` number. A page is the fiscal sheet when the text has `FACTURA` together with a fiscal token, when `N° DE CONTROL` appears with the forma libre markers, or when the page carries the forma libre title or the crédito fiscal footer. Comprobantes, informes, and pages that only repeat a RIF stay attachments. PowerPoint packets are read from the photograph on each slide. The one binary `.ppt` file is left unreadable.

| Page label | Pages |
| --- | ---: |
| Fiscal invoice sheet | {fiscal:,} |
| Attachment | {attachment:,} |
| Unreadable | {unreadable:,} |

Evidence in `invoice-pages.csv` names the matched tokens. It does not copy the page text.
"""
    md_path = OUT_DIR / "Avila-backup-invoices.md"
    existing = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""
    marker = "\n## Page pass\n"
    if marker in existing:
        existing = existing.split(marker)[0].rstrip() + "\n"
    md_path.write_text(existing.rstrip() + "\n" + section, encoding="utf-8")
    html_path = OUT_DIR / "Avila-backup-invoices.html"
    if html_path.is_file():
        html = html_path.read_text(encoding="utf-8")
        block = (
            "<h2>Page pass</h2>"
            "<table><thead><tr><th>Page label</th><th>Pages</th></tr></thead><tbody>"
            f"<tr><td>Fiscal invoice sheet</td><td>{fiscal:,}</td></tr>"
            f"<tr><td>Attachment</td><td>{attachment:,}</td></tr>"
            f"<tr><td>Unreadable</td><td>{unreadable:,}</td></tr>"
            "</tbody></table>"
            "<p>A page counts as the fiscal sheet when OCR finds FACTURA with a fiscal token, "
            "N° de control with the forma libre markers, the forma libre title, or the crédito fiscal footer. "
            "Comprobantes and informes stay attachments.</p>"
        )
        html = re.sub(r"<h2>Page pass</h2>.*?(?=<footer>|</main>)", "", html, flags=re.S)
        html = html.replace("<footer>", block + "\n  <footer>")
        html_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
