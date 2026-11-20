import { NextRequest, NextResponse } from "next/server";
import { get } from "@vercel/blob";
import { requireReaderApi } from "@/lib/auth";
import { sql } from "@/lib/db";
import { ensureEnv } from "@/lib/env";

export const dynamic = "force-dynamic";

/**
 * Stream document bytes for authenticated staff.
 * Supports public blob URLs (legacy) and private pathnames via @vercel/blob get().
 */
export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ documentId: string }> },
) {
  const denied = await requireReaderApi();
  if (denied) return denied;

  ensureEnv();
  const { documentId } = await context.params;
  const db = sql();
  const [doc] = await db`
    SELECT blob_url, blob_pathname, content_type, upload_status::text AS upload_status
    FROM avila.document
    WHERE id = ${documentId}::uuid
  `;
  if (!doc || doc.upload_status !== "uploaded") {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  const headers = new Headers();
  headers.set("Cache-Control", "private, max-age=300");

  // Prefer private pathname fetch when configured / available.
  if (doc.blob_pathname && process.env.BLOB_READ_WRITE_TOKEN) {
    try {
      const result = await get(doc.blob_pathname, {
        access: "private",
        token: process.env.BLOB_READ_WRITE_TOKEN,
      });
      if (result?.stream) {
        headers.set(
          "Content-Type",
          doc.content_type || result.blob.contentType || "image/png",
        );
        return new NextResponse(result.stream, { status: 200, headers });
      }
    } catch {
      // Fall through to public URL fetch for stores still on public access.
    }
  }

  if (!doc.blob_url) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  const upstream = await fetch(doc.blob_url);
  if (!upstream.ok) {
    return NextResponse.json({ error: "blob_fetch_failed" }, { status: 502 });
  }
  headers.set(
    "Content-Type",
    doc.content_type || upstream.headers.get("content-type") || "image/png",
  );
  return new NextResponse(upstream.body, { status: 200, headers });
}
