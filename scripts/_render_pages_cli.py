#!/usr/bin/env python3
"""CLI: render backup pages to temp images. Prints JSON {images, error, cleanup_dir}."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ocr_invoice_pages import BACKUP, _render_pdf

PPTX_RENDER = Path(__file__).resolve().parent / "_render_pptx.mjs"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: _render_pages_cli.py <relative-backup-path>", file=sys.stderr)
        sys.exit(2)
    relative = sys.argv[1]
    source = BACKUP / relative
    if not source.is_file():
        print(json.dumps({"images": [], "error": "missing", "cleanup_dir": None}))
        return

    suffix = source.suffix.lower()
    tmp = tempfile.mkdtemp(prefix="avila-retry-")
    folder = Path(tmp)
    images: list[str | None] = []
    error = ""

    if suffix == ".pdf":
        pages, error = _render_pdf(source, folder)
        images = [str(p) for p in pages]
    elif suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        images = [str(source)]
    elif suffix in {".pptx", ".potx"}:
        # Node unzip path avoids broken Homebrew Python 3.14 pyexpat.
        proc = subprocess.run(
            ["node", str(PPTX_RENDER), str(source), str(folder)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            error = (proc.stderr or "pptx_render_failed")[:200]
        else:
            payload = json.loads(proc.stdout)
            images = payload.get("images") or []
            error = payload.get("error") or ""
    else:
        error = f"unsupported:{suffix}"

    print(json.dumps({"images": images, "error": error, "cleanup_dir": tmp}))


if __name__ == "__main__":
    main()
