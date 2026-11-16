#!/usr/bin/env node
/**
 * Re-upload documents with upload_status=failed using the current BLOB_* env.
 * Renders each source file via a tiny Python helper (no psycopg required).
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, existsSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const BLOB_PUT = join(ROOT, "scripts", "blob_put.mjs");
const RENDER_HELPER = join(ROOT, "scripts", "_render_pages_cli.py");

function loadEnv() {
  const env = {};
  const text = readFileSync(join(ROOT, ".env"), "utf8");
  for (const line of text.split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    const k = t.slice(0, i).trim();
    let v = t.slice(i + 1).trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    env[k] = v;
  }
  return env;
}

function putBlob(env, pathname, filePath) {
  const proc = spawnSync("node", [BLOB_PUT, pathname, filePath], {
    env: { ...process.env, ...pickBlob(env) },
    encoding: "utf8",
  });
  if (proc.status !== 0) {
    throw new Error((proc.stderr || proc.stdout || "blob_put failed").slice(0, 300));
  }
  return JSON.parse(proc.stdout);
}

function pickBlob(env) {
  const out = {};
  for (const k of Object.keys(env)) {
    if (k.startsWith("BLOB")) out[k] = env[k];
  }
  return out;
}

function renderPages(relative) {
  const proc = spawnSync("python3", [RENDER_HELPER, relative], {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
  });
  if (proc.status !== 0) {
    throw new Error((proc.stderr || proc.stdout || "render failed").slice(0, 300));
  }
  return JSON.parse(proc.stdout);
}

async function main() {
  const limitFiles = Number(process.argv.find((a) => a.startsWith("--limit="))?.slice(8) || 0);
  const onlyBlobErrors = process.argv.includes("--blob-errors");
  const env = loadEnv();
  const url = env.DATABASE_URL_UNPOOLED || env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL missing");
  if (!env.BLOB_READ_WRITE_TOKEN) throw new Error("BLOB_READ_WRITE_TOKEN missing");

  const client = new pg.Client({ connectionString: url, ssl: { rejectUnauthorized: false } });
  await client.connect();

  const { rows: failed } = await client.query(
    `
    SELECT d.id, d.page_index, d.blob_pathname, d.document_type,
           sf.backup_path
    FROM avila.document d
    JOIN avila.source_file sf ON sf.id = d.source_file_id
    WHERE d.upload_status = 'failed'
      AND ($1::boolean = false OR d.upload_error ILIKE '%BlobError%' OR d.upload_error ILIKE '%private access%')
    ORDER BY sf.backup_path, d.page_index
  `,
    [onlyBlobErrors],
  );
  console.log(`Failed documents: ${failed.length}`);

  const byPath = new Map();
  for (const row of failed) {
    if (!byPath.has(row.backup_path)) byPath.set(row.backup_path, []);
    byPath.get(row.backup_path).push(row);
  }
  if (limitFiles > 0) {
    const keep = [...byPath.keys()].slice(0, limitFiles);
    for (const key of [...byPath.keys()]) {
      if (!keep.includes(key)) byPath.delete(key);
    }
    console.log(`Limiting to ${byPath.size} source file(s)`);
  }

  let uploaded = 0;
  let stillFailed = 0;
  let fileIndex = 0;
  for (const [backupPath, docs] of byPath) {
    fileIndex += 1;
    let images = [];
    let renderError = "";
    let cleanupDir = null;
    try {
      const rendered = renderPages(backupPath);
      images = rendered.images || [];
      renderError = rendered.error || "";
      cleanupDir = rendered.cleanup_dir || null;
    } catch (err) {
      renderError = String(err.message || err);
    }

    for (const doc of docs) {
      const image = images[doc.page_index - 1] || null;
      if (!image || !existsSync(image)) {
        await client.query(
          `UPDATE avila.document
           SET upload_status='failed', upload_error=$1, updated_at=now()
           WHERE id=$2`,
          [renderError || "no_image", doc.id],
        );
        stillFailed += 1;
        continue;
      }
      try {
        const pathname =
          doc.blob_pathname ||
          `avila/invoices/retry/${createHash("sha256").update(String(doc.id)).digest("hex").slice(0, 16)}/${doc.page_index}.png`;
        const blob = putBlob(env, pathname, image);
        const bytes = readFileSync(image);
        const sha = createHash("sha256").update(bytes).digest("hex");
        await client.query(
          `UPDATE avila.document SET
             blob_pathname=$1,
             blob_url=$2,
             content_type=$3,
             byte_size=$4,
             sha256=$5,
             upload_status='uploaded',
             upload_error=NULL,
             updated_at=now()
           WHERE id=$6`,
          [
            blob.pathname || pathname,
            blob.url,
            blob.contentType || "image/png",
            bytes.length,
            sha,
            doc.id,
          ],
        );
        uploaded += 1;
      } catch (err) {
        await client.query(
          `UPDATE avila.document
           SET upload_status='failed', upload_error=$1, updated_at=now()
           WHERE id=$2`,
          [String(err.message || err).slice(0, 500), doc.id],
        );
        stillFailed += 1;
      }
    }

    if (cleanupDir) {
      spawnSync("rm", ["-rf", cleanupDir]);
    }

    if (fileIndex % 10 === 0 || fileIndex === byPath.size) {
      console.log(
        `Files ${fileIndex}/${byPath.size} uploaded=${uploaded} still_failed=${stillFailed}`,
      );
    }
  }

  const { rows: counts } = await client.query(`
    SELECT upload_status, count(*)::int AS n
    FROM avila.document
    GROUP BY 1 ORDER BY 2 DESC
  `);
  console.log("Done", { uploaded, stillFailed, counts });
  await client.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
