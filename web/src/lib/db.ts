import { neon } from "@neondatabase/serverless";
import { ensureEnv } from "./env";

export { DOCUMENT_TYPE_LABELS } from "./document-labels";

export function sql() {
  ensureEnv();
  const url = process.env.DATABASE_URL || process.env.DATABASE_URL_UNPOOLED;
  if (!url) {
    throw new Error("DATABASE_URL is not configured");
  }
  return neon(url);
}

export const UPLOAD_STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente",
  uploaded: "Subido",
  failed: "Fallido",
  skipped: "Omitido",
};

export const ROLE_LABELS: Record<string, string> = {
  titular: "Titular",
  beneficiario: "Beneficiario",
  unknown: "Sin rol claro",
};

export const IDENTITY_TYPE_LABELS: Record<string, string> = {
  cedula: "Cédula",
  pasaporte: "Pasaporte",
  rif: "RIF",
  unknown: "Sin tipo",
};
