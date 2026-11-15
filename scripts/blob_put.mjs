#!/usr/bin/env node
/**
 * Put one Blob object. Args: pathname filePath
 * Reads BLOB_READ_WRITE_TOKEN from the environment.
 * Set BLOB_ACCESS=private (default) for private stores, or public for legacy stores.
 * Prints JSON { url, pathname, contentType } on success.
 */
import { readFileSync } from "node:fs";
import { put } from "@vercel/blob";

const [pathname, filePath] = process.argv.slice(2);
if (!pathname || !filePath) {
  console.error("Usage: blob_put.mjs <pathname> <filePath>");
  process.exit(2);
}
if (!process.env.BLOB_READ_WRITE_TOKEN) {
  console.error("BLOB_READ_WRITE_TOKEN is missing");
  process.exit(2);
}

const access = process.env.BLOB_ACCESS === "public" ? "public" : "private";

const body = readFileSync(filePath);
const contentType =
  filePath.toLowerCase().endsWith(".jpg") || filePath.toLowerCase().endsWith(".jpeg")
    ? "image/jpeg"
    : filePath.toLowerCase().endsWith(".png")
      ? "image/png"
      : "application/octet-stream";

const blob = await put(pathname, body, {
  access,
  addRandomSuffix: false,
  contentType,
  token: process.env.BLOB_READ_WRITE_TOKEN,
  allowOverwrite: true,
});

process.stdout.write(
  JSON.stringify({
    url: blob.url,
    pathname: blob.pathname,
    contentType: blob.contentType || contentType,
    access,
  }),
);
