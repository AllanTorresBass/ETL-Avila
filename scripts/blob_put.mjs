#!/usr/bin/env node
/**
 * Put one Blob object. Args: pathname filePath
 * Reads BLOB_READ_WRITE_TOKEN from the environment.
 * BLOB_ACCESS=private|public (default private). If the token's store rejects
 * that access mode, automatically retries with the opposite mode so a mismatched
 * .env cannot leave every document as "failed".
 * Prints JSON { url, pathname, contentType, access } on success.
 */
import { readFileSync } from "node:fs";
import { put } from "@vercel/blob";

const [pathname, filePath] = process.argv.slice(2);
if (!pathname || !filePath) {
  console.error("Usage: blob_put.mjs <pathname> <filePath>");
  process.exit(2);
}
const token = (process.env.BLOB_READ_WRITE_TOKEN || "").trim().replace(/^["']|["']$/g, "");
if (!token) {
  console.error("BLOB_READ_WRITE_TOKEN is missing");
  process.exit(2);
}

const preferred = process.env.BLOB_ACCESS === "public" ? "public" : "private";
const fallback = preferred === "private" ? "public" : "private";

const body = readFileSync(filePath);
const isJpeg = body[0] === 0xff && body[1] === 0xd8 && body[2] === 0xff;
const isPng = body.subarray(0, 4).toString("latin1") === "\x89PNG";
const contentType = isJpeg ? "image/jpeg" : isPng ? "image/png" : "application/octet-stream";

async function putWithAccess(access) {
  return put(pathname, body, {
    access,
    addRandomSuffix: false,
    contentType,
    token,
    allowOverwrite: true,
  });
}

function isAccessMismatch(err) {
  const msg = String(err?.message || err);
  return (
    msg.includes("Cannot use private access on a public store") ||
    msg.includes("Cannot use public access on a private store")
  );
}

let access = preferred;
let blob;
try {
  blob = await putWithAccess(access);
} catch (err) {
  if (!isAccessMismatch(err)) throw err;
  access = fallback;
  blob = await putWithAccess(access);
}

process.stdout.write(
  JSON.stringify({
    url: blob.url,
    pathname: blob.pathname,
    contentType: blob.contentType || contentType,
    access,
  }),
);
