"""Walk Avila-backup and write the file-level invoice inventory.

Reads the backup. Writes output/invoices/invoices.csv plus a Markdown and
HTML summary. Does not move or rename backup files.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from invoice_rules import classify

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "Avila-backup"
OUT_DIR = ROOT / "output" / "invoices"

CSV_FIELDS = [
    "path",
    "label",
    "rule_id",
    "confidence",
    "invoice_number",
    "invoice_numbers",
    "invoice_range",
    "related_invoice_number",
    "account",
    "account_labels",
    "account_raw",
    "month",
    "year",
    "lote",
    "parte",
    "lot",
    "workflow",
    "channel",
    "extension",
    "pages",
    "bytes",
    "duplicate_group",
]

PAGE_LABELS = {"invoice_packet", "needs_page_check"}


def _page_count(path: str) -> str:
    try:
        proc = subprocess.run(
            ["pdfinfo", path],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            parts = line.split()
            return parts[1] if len(parts) > 1 else ""
    return ""


def _slide_count(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            slides = [
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
        return str(len(slides))
    except (OSError, zipfile.BadZipFile):
        return ""


def walk_backup() -> tuple[list[dict], Counter]:
    rows = []
    skipped = Counter()
    for dirpath, dirnames, filenames in os.walk(BACKUP):
        dirnames[:] = [name for name in dirnames if name != ".DS_Store"]
        for filename in filenames:
            if filename == ".DS_Store" or filename.startswith("._"):
                skipped["finder_metadata"] += 1
                continue
            full = Path(dirpath) / filename
            relative = full.relative_to(BACKUP).as_posix()
            result = classify(relative)
            if result.rule_id == "skipped_sidecar":
                skipped[result.rule_id] += 1
                continue
            try:
                size = full.stat().st_size
            except OSError:
                size = 0
            row = result.as_row()
            row["path"] = relative
            row["extension"] = full.suffix.lower()
            row["pages"] = ""
            row["bytes"] = size
            rows.append(row)
    return rows, skipped


def fill_page_counts(rows: list[dict]) -> None:
    pdfs = []
    for index, row in enumerate(rows):
        if row["label"] not in PAGE_LABELS:
            continue
        full = str(BACKUP / row["path"])
        ext = row["extension"]
        if ext == ".pdf":
            pdfs.append((index, full))
        elif ext in {".pptx", ".potx"}:
            row["pages"] = _slide_count(full)
    if not pdfs:
        return
    workers = min(8, os.cpu_count() or 4)

    def job(item):
        index, full = item
        return index, _page_count(full)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, pages in pool.map(job, pdfs):
            rows[index]["pages"] = pages


def write_csv(rows: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "invoices.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return target


def _gib(num_bytes: int) -> str:
    return f"{num_bytes / 1024 ** 3:.2f}"


def _table(headers: list[str], body: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in body:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _html_table(headers: list[str], body: list[list]) -> str:
    head = "".join(f"<th>{escape(str(cell))}</th>" for cell in headers)
    rows = []
    for row in body:
        cells = "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def summarize(rows: list[dict], skipped: Counter) -> dict:
    by_label = Counter()
    bytes_by_label = Counter()
    by_rule = Counter()
    packet_account = Counter()
    packet_year = Counter()
    packet_ext = Counter()
    packet_confidence = Counter()
    packet_channel = Counter()
    candidate_rules = Counter()
    duplicate_sizes = Counter()
    pages_known = 0
    page_sum = 0
    for row in rows:
        by_label[row["label"]] += 1
        bytes_by_label[row["label"]] += int(row["bytes"] or 0)
        by_rule[row["rule_id"]] += 1
        if row["label"] == "invoice_packet":
            packet_account[row["account"] or "(no account token)"] += 1
            packet_year[row["year"] or "(no year)"] += 1
            packet_ext[row["extension"] or "(none)"] += 1
            packet_confidence[row["confidence"] or "(none)"] += 1
            packet_channel[row["channel"]] += 1
            if row["pages"].isdigit():
                pages_known += 1
                page_sum += int(row["pages"])
        if row["label"] == "needs_page_check":
            candidate_rules[row["rule_id"]] += 1
        if row["duplicate_group"]:
            duplicate_sizes[row["duplicate_group"]] += 1
    copies = Counter(duplicate_sizes.values())
    return {
        "files": len(rows),
        "skipped": skipped,
        "by_label": by_label,
        "bytes_by_label": bytes_by_label,
        "by_rule": by_rule,
        "packet_account": packet_account,
        "packet_year": packet_year,
        "packet_ext": packet_ext,
        "packet_confidence": packet_confidence,
        "packet_channel": packet_channel,
        "candidate_rules": candidate_rules,
        "duplicate_groups": len(duplicate_sizes),
        "duplicate_groups_multi": sum(1 for size in duplicate_sizes.values() if size > 1),
        "copy_sizes": copies,
        "pages_known": pages_known,
        "page_sum": page_sum,
    }


def write_reports(rows: list[dict], skipped: Counter) -> None:
    stats = summarize(rows, skipped)
    labels = ["invoice_packet", "needs_page_check", "supporting", "template", "not_invoice"]
    label_rows = []
    for label in labels:
        label_rows.append([
            label,
            f"{stats['by_label'][label]:,}",
            _gib(stats["bytes_by_label"][label]),
        ])
    account_rows = [
        [name, f"{count:,}"]
        for name, count in stats["packet_account"].most_common()
    ]
    rule_rows = [
        [rule, f"{count:,}"]
        for rule, count in stats["by_rule"].most_common()
        if rule != "default_not_invoice" and rule != "scan_outside_invoice"
    ]
    year_rows = [[year, f"{count:,}"] for year, count in sorted(stats["packet_year"].items())]
    ext_rows = [[ext, f"{count:,}"] for ext, count in stats["packet_ext"].most_common()]
    channel_rows = [
        [name, f"{count:,}"] for name, count in stats["packet_channel"].most_common()
    ]
    confidence_rows = [
        [name, f"{count:,}"] for name, count in stats["packet_confidence"].most_common()
    ]
    candidate_rows = [
        [name, f"{count:,}"] for name, count in stats["candidate_rules"].most_common()
    ]
    avg_pages = (
        f"{stats['page_sum'] / stats['pages_known']:.1f}"
        if stats["pages_known"]
        else "n/a"
    )
    skipped_n = sum(stats["skipped"].values())

    md = f"""# Avila-backup invoice inventory

File-level classification of `{BACKUP.name}`. A fiscal invoice here is a file named as the billed document (`FACT`, `FAC`, or `FACTURA`), not a clinical page stored beside it. Scanner pages inside a folder whose title carries a `FACT` range are candidates: the folder proves the batch is invoices, and the page pass decides which images are the fiscal sheet.

This summary has counts and invoice numbers only. Paths, which can contain patient names, are in `invoices.csv`.

## Counts

| Measure | Value |
| --- | ---: |
| Files classified | {stats['files']:,} |
| Sidecars omitted (shortcuts, temp files, archives) | {skipped_n:,} |
| Invoice packets | {stats['by_label']['invoice_packet']:,} |
| Candidate pages awaiting the page pass | {stats['by_label']['needs_page_check']:,} |
| Supporting documents that mention an invoice | {stats['by_label']['supporting']:,} |
| Templates | {stats['by_label']['template']:,} |
| Not an invoice | {stats['by_label']['not_invoice']:,} |
| Invoice-packet bytes | {_gib(stats['bytes_by_label']['invoice_packet'])} GB |
| Packets with a known page count | {stats['pages_known']:,} |
| Average pages in those packets | {avg_pages} |
| Distinct invoice numbers on named packets | {stats['duplicate_groups']:,} |
| Invoice numbers stored as more than one file | {stats['duplicate_groups_multi']:,} |

{_table(["Label", "Files", "GB"], label_rows)}

## Why a file was labeled

Rules run in order: skip junk, then templates, then a clinical or register role, then a named invoice, then an unnamed scan whose folder title contains a `FACT` number. `default_not_invoice` and `scan_outside_invoice` are the rest of the backup and are omitted from this table.

{_table(["Rule", "Files"], rule_rows)}

## Invoice packets

Confidence is `high` when the file name itself contains `FACT` plus a number, and `medium` for `FAC` or for a `FACT` word whose number comes from the folder.

{_table(["Confidence", "Packets"], confidence_rows)}

{_table(["Extension", "Packets"], ext_rows)}

{_table(["Channel", "Packets"], channel_rows)}

{_table(["Account token in the path", "Packets"], account_rows)}

{_table(["Year token", "Packets"], year_rows)}

`mixed` means the folder title names more than one account. The original title is in the `account_raw` column of the CSV.

## Candidate pages

These files are not labeled invoices. They are `IMG` or `Escáner` pages, or a `GPSPDF` bundle, sitting under a folder title that contains a `FACT` number or range. One number is not assigned to each page.

{_table(["Rule", "Files"], candidate_rows)}

## Duplicates

The same invoice number on a PDF and a PowerPoint, including a copy under `procesadas`, shares one `duplicate_group` (`fact-<number>`). Groups with more than one file: {stats['duplicate_groups_multi']:,}.

## What this file pass does not decide

Named packets are usually multi-page image binders exported from PowerPoint, with no text layer. The packet is the invoice file. Which pages inside it are the fiscal sheet is the page pass (`invoice-pages.csv`). Candidate scans in a `FACT 18653-18819` style folder are the same problem: several images per invoice, so the range stays on the folder and the page stays unnumbered until OCR.
"""
    (OUT_DIR / "Avila-backup-invoices.md").write_text(md, encoding="utf-8")

    def section(title, headers, body):
        return f"<h2>{escape(title)}</h2>{_html_table(headers, body)}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Avila-backup invoice inventory</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink: #0A2A6B;
    --navy: #0A1F4D;
    --link: #033CA0;
    --sky: #5BB2F5;
    --green: #6CC24A;
    --green-deep: #0F7A33;
    --page: #F4F8FC;
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--ink);
    font-family: Montserrat, sans-serif;
    font-size: 16px;
    line-height: 1.55;
    font-weight: 400;
    -webkit-font-smoothing: antialiased;
  }}
  ::selection {{ background: var(--green); color: #fff; }}
  ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
  ::-webkit-scrollbar-track {{ background: #EBF4FC; }}
  ::-webkit-scrollbar-thumb {{ background: var(--sky); border-radius: 999px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: var(--link); }}
  header {{
    background: var(--ink);
    color: #fff;
    padding: 48px 0 72px;
  }}
  .wrap {{ max-width: 72rem; margin: 0 auto; padding: 0 16px; }}
  .kicker {{
    margin: 0 0 10px;
    color: var(--sky);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }}
  h1 {{
    margin: 0 0 12px;
    font-weight: 500;
    font-size: 2.25rem;
    letter-spacing: -0.03em;
    line-height: 1.1;
  }}
  header p {{ max-width: 42rem; margin: 0; color: rgba(255,255,255,0.88); font-weight: 300; }}
  header p.kicker {{ max-width: none; margin: 0 0 10px; color: var(--sky); font-weight: 500; }}
  main {{ max-width: 72rem; margin: -40px auto 0; padding: 0 16px 64px; }}
  h2 {{
    margin: 40px 0 12px;
    color: var(--ink);
    font-size: 1.5rem;
    font-weight: 500;
    letter-spacing: -0.02em;
  }}
  p {{ margin: 8px 0 16px; color: #475569; font-size: 0.875rem; }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }}
  .card {{
    background: #fff;
    border: 1px solid #f1f5f9;
    border-radius: 24px;
    box-shadow: 0 1px 2px rgba(10, 42, 107, 0.06);
    padding: 24px;
    transition: transform 0.3s, box-shadow 0.3s;
  }}
  .card:hover {{
    transform: translateY(-6px);
    box-shadow: 0 24px 40px -16px rgba(10, 42, 107, 0.28);
  }}
  .num {{
    color: var(--ink);
    font-size: 1.75rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
  }}
  .lbl {{
    margin-top: 8px;
    color: #64748b;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: #fff;
    border: 1px solid #f1f5f9;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(10, 42, 107, 0.06);
    margin: 0 0 8px;
    font-size: 0.875rem;
  }}
  th, td {{ text-align: left; padding: 12px 16px; border-bottom: 1px solid #f1f5f9; }}
  tr:last-child td {{ border-bottom: none; }}
  th {{
    background: var(--page);
    color: var(--ink);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  td:nth-child(n+2), th:nth-child(n+2) {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  tbody tr:hover td {{ background: #F4F8FC; }}
  footer {{
    margin-top: 28px;
    padding: 20px 24px;
    background: var(--navy);
    color: rgba(255,255,255,0.86);
    border-radius: 24px;
    font-size: 13px;
    line-height: 1.5;
  }}
  @media (min-width: 640px) {{
    .wrap, main {{ padding-left: 24px; padding-right: 24px; }}
  }}
  @media (max-width: 900px) {{
    h1 {{ font-size: 1.75rem; }}
    .cards {{ grid-template-columns: 1fr 1fr; }}
  }}
  @media (max-width: 560px) {{
    .cards {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <p class="kicker">Ávila GPS</p>
    <h1>Invoice inventory</h1>
    <p>File-level classification. A fiscal invoice is a file named as the billed document. Clinical pages that only mention an invoice number are supporting documents. Scanner pages in a FACT-range folder wait for the page pass.</p>
  </div>
</header>
<main>
  <div class="cards">
    <div class="card"><div class="num">{stats['by_label']['invoice_packet']:,}</div><div class="lbl">Invoice packets</div></div>
    <div class="card"><div class="num">{stats['by_label']['needs_page_check']:,}</div><div class="lbl">Candidate pages</div></div>
    <div class="card"><div class="num">{stats['by_label']['supporting']:,}</div><div class="lbl">Supporting files</div></div>
    <div class="card"><div class="num">{_gib(stats['bytes_by_label']['invoice_packet'])} GB</div><div class="lbl">Packet size</div></div>
  </div>
  {section("Labels", ["Label", "Files", "GB"], label_rows)}
  {section("Rules, excluding the general not-invoice bucket", ["Rule", "Files"], rule_rows)}
  {section("Packet confidence", ["Confidence", "Packets"], confidence_rows)}
  {section("Packet extension", ["Extension", "Packets"], ext_rows)}
  {section("Packet channel", ["Channel", "Packets"], channel_rows)}
  {section("Account token on invoice packets", ["Account", "Packets"], account_rows)}
  {section("Year token on invoice packets", ["Year", "Packets"], year_rows)}
  {section("Candidate pages", ["Rule", "Files"], candidate_rows)}
  <h2>Duplicates and page depth</h2>
  <p>Distinct invoice numbers on named packets: {stats['duplicate_groups']:,}. Numbers stored as more than one file: {stats['duplicate_groups_multi']:,}. Packets with a known page count: {stats['pages_known']:,}, averaging {avg_pages} pages. Those extra pages are attachments until the page pass marks the fiscal sheet.</p>
  <p>Sidecars omitted from the CSV (shortcuts, temp files, archives): {skipped_n:,}. Files classified: {stats['files']:,}.</p>
  <footer>Paths are in invoices.csv and can contain patient names. This page lists counts only. The same summary is in Avila-backup-invoices.md.</footer>
</main>
</body>
</html>
"""
    (OUT_DIR / "Avila-backup-invoices.html").write_text(html, encoding="utf-8")


def main() -> None:
    if not BACKUP.is_dir():
        sys.exit(f"Backup not found: {BACKUP}")
    print("Walking", BACKUP)
    rows, skipped = walk_backup()
    print(f"Classified {len(rows):,} files; measuring packet page counts")
    fill_page_counts(rows)
    csv_path = write_csv(rows)
    write_reports(rows, skipped)
    labels = Counter(row["label"] for row in rows)
    print("Labels:", dict(labels))
    print("Wrote", csv_path)


if __name__ == "__main__":
    main()
