import { neon } from "@neondatabase/serverless";
import { ensureEnv } from "./env";

export function sql() {
  ensureEnv();
  const url = process.env.DATABASE_URL || process.env.DATABASE_URL_UNPOOLED;
  if (!url) {
    throw new Error("DATABASE_URL is not configured");
  }
  return neon(url);
}

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  factura_fiscal: "Factura fiscal",
  cedula_identidad: "Cédula de identidad",
  pasaporte: "Pasaporte",
  carnet: "Carnet",
  egreso: "Egreso",
  ingreso: "Ingreso",
  informe_medico: "Informe médico",
  comprobante: "Comprobante",
  carta_aval: "Carta aval",
  presupuesto: "Presupuesto",
  laboratorio: "Laboratorio",
  imagenologia: "Imagenología",
  orden_servicio: "Orden de servicio",
  otro_anexo: "Otro anexo",
  ilegible: "Ilegible",
};

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
