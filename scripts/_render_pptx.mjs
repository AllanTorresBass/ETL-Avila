#!/usr/bin/env node
/**
 * Extract one largest raster image per PPTX slide (same rule as Python _render_office).
 * Avoids Python xml.etree (broken pyexpat on some Homebrew 3.14 installs).
 * Args: pptxPath outDir → JSON { images, error }
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join, normalize } from "node:path";
import { spawnSync } from "node:child_process";

const [pptxPath, outDir] = process.argv.slice(2);
if (!pptxPath || !outDir) {
  console.error("Usage: _render_pptx.mjs <pptxPath> <outDir>");
  process.exit(2);
}

const RASTER = new Set([".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"]);

function unzipList(path) {
  const proc = spawnSync("unzip", ["-Z1", path], { encoding: "utf8" });
  if (proc.status !== 0) throw new Error("BadZipFile");
  return new Set(
    proc.stdout
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

function unzipRead(path, member) {
  const proc = spawnSync("unzip", ["-p", path, member], {
    encoding: "buffer",
    maxBuffer: 50 * 1024 * 1024,
  });
  if (proc.status !== 0) throw new Error(`missing:${member}`);
  return proc.stdout;
}

function parseRels(xml) {
  const map = {};
  const re = /<Relationship\b([^>]+)\/>/g;
  let m;
  while ((m = re.exec(xml))) {
    const attrs = m[1];
    const id = /Id="([^"]+)"/.exec(attrs)?.[1];
    const target = /Target="([^"]+)"/.exec(attrs)?.[1] || "";
    const type = /Type="([^"]+)"/.exec(attrs)?.[1] || "";
    if (id) map[id] = { target, type };
  }
  return map;
}

function normPpt(path) {
  return normalize(path).replace(/\\/g, "/").replace(/^\.\//, "");
}

try {
  const names = unzipList(pptxPath);
  if (!names.has("ppt/presentation.xml") || !names.has("ppt/_rels/presentation.xml.rels")) {
    process.stdout.write(JSON.stringify({ images: [], error: "unsupported:office_layout" }));
    process.exit(0);
  }

  const presentation = unzipRead(pptxPath, "ppt/presentation.xml").toString("utf8");
  const deckRels = parseRels(
    unzipRead(pptxPath, "ppt/_rels/presentation.xml.rels").toString("utf8"),
  );

  const slides = [];
  const sldRe = /<p:sldId\b([^>]+)\/>/g;
  let sm;
  while ((sm = sldRe.exec(presentation))) {
    const rid =
      /r:id="([^"]+)"/.exec(sm[1])?.[1] ||
      /id="(rId[^"]+)"/.exec(sm[1])?.[1];
    if (!rid || !deckRels[rid]) continue;
    let slidePath = String(deckRels[rid].target).replace(/^\//, "");
    if (!slidePath.startsWith("ppt/")) slidePath = normPpt(join("ppt", slidePath));
    slides.push(slidePath);
  }

  if (!slides.length) {
    process.stdout.write(JSON.stringify({ images: [], error: "no_pages" }));
    process.exit(0);
  }

  mkdirSync(outDir, { recursive: true });
  const images = [];
  for (let index = 0; index < slides.length; index++) {
    const slidePath = slides[index];
    const relPath = normPpt(join(dirname(slidePath), "_rels", `${basename(slidePath)}.rels`));
    if (!names.has(relPath)) {
      images.push(null);
      continue;
    }
    const rels = parseRels(unzipRead(pptxPath, relPath).toString("utf8"));
    let bestName = null;
    let bestSize = -1;
    for (const rel of Object.values(rels)) {
      if (!rel.type.endsWith("/image")) continue;
      let media = normPpt(join(dirname(slidePath), rel.target)).replace(/^\//, "");
      if (!names.has(media)) continue;
      const ext = media.slice(media.lastIndexOf(".")).toLowerCase();
      if (!RASTER.has(ext)) continue;
      const buf = unzipRead(pptxPath, media);
      if (buf.length > bestSize) {
        bestSize = buf.length;
        bestName = media;
      }
    }
    if (!bestName) {
      images.push(null);
      continue;
    }
    const ext = bestName.slice(bestName.lastIndexOf(".")).toLowerCase() || ".png";
    const out = join(outDir, `page-${String(index + 1).padStart(2, "0")}${ext}`);
    writeFileSync(out, unzipRead(pptxPath, bestName));
    images.push(out);
  }
  process.stdout.write(JSON.stringify({ images, error: "" }));
} catch (err) {
  process.stdout.write(
    JSON.stringify({
      images: [],
      error: `render_failed:${String(err.message || err).slice(0, 120)}`,
    }),
  );
}
