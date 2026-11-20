import { sql } from "@/lib/db";

export type UploadedBlobRow = {
  blob_url: string | null;
  blob_pathname: string | null;
  content_type: string | null;
  upload_status: string;
};

export async function getUploadedDocumentBlob(documentId: string): Promise<UploadedBlobRow | null> {
  const db = sql();
  const [doc] = await db`
    SELECT blob_url, blob_pathname, content_type, upload_status::text AS upload_status
    FROM avila.document
    WHERE id = ${documentId}::uuid
  `;
  const row = doc as UploadedBlobRow | undefined;
  if (!row || row.upload_status !== "uploaded") return null;
  return row;
}
