import { sql } from "@/lib/db";
import { queryAtenciones, type AtencionRow } from "@/lib/medico-data";

export const FACTURA_AUTH_LIMIT = 20;

export type FacturaInvoice = {
  id: string;
  invoice_number: string | null;
  year: string | null;
  month: string | null;
  lote: string | null;
  account: string | null;
  account_code: string | null;
  control_number: string | null;
  issue_date: string | Date | null;
  workflow: string | null;
  channel: string | null;
  duplicate_group: string | null;
  invoice_range: string | null;
};

export type FacturaPerson = {
  id: string;
  identity_number: string | null;
  full_name: string | null;
  role: string;
  parentesco: string | null;
};

export type FacturaAuthLine = {
  id: string;
  clave_rms: string | null;
  diagnosis: string | null;
  service_description: string | null;
  amount_bs: string | number | null;
  amount_usd: string | number | null;
  person_id: string | null;
  service_date: string | Date | null;
  contratante: string | null;
  provider_name: string | null;
  person_name: string | null;
  identity_number: string | null;
};

export type FacturaSourceFile = {
  id: string;
  file_label: string | null;
  extension: string | null;
  pages: number | null;
  rule_id: string | null;
  backup_path: string | null;
};

export type FacturaDoc = {
  id: string;
  page_index: number | null;
  document_type: string;
  upload_status: string;
  source_file_id: string | null;
};

export type FacturaDetail = {
  invoice: FacturaInvoice;
  people: FacturaPerson[];
  authTotal: number;
  authLines: FacturaAuthLine[];
  files: FacturaSourceFile[];
  docs: FacturaDoc[];
  docTotal: number;
  fileFilter: string;
  activeFile: FacturaSourceFile | undefined;
  atenciones: AtencionRow[];
};

export async function getFacturaDetail(id: string, fileRaw: string): Promise<FacturaDetail | null> {
  const db = sql();
  const [invoice] = await db`
    SELECT i.*, a.legal_name AS account, a.code AS account_code
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE i.id = ${id}::uuid
  `;
  if (!invoice) return null;

  const people = await db`
    SELECT p.id, p.identity_number, p.full_name, ip.role::text AS role, ip.parentesco
    FROM avila.invoice_person ip
    JOIN avila.person p ON p.id = ip.person_id
    WHERE ip.invoice_id = ${id}::uuid
    ORDER BY CASE ip.role WHEN 'titular' THEN 0 WHEN 'beneficiario' THEN 1 ELSE 2 END, p.full_name
  `;

  const [authCountRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.authorization_line
    WHERE invoice_id = ${id}::uuid
  `;
  const authTotal = authCountRow?.n ?? 0;

  const authLines = await db`
    SELECT al.id, al.clave_rms, al.diagnosis, al.service_description, al.amount_bs, al.amount_usd,
           al.person_id, al.service_date, al.contratante, al.provider_name,
           p.full_name AS person_name, p.identity_number
    FROM avila.authorization_line al
    LEFT JOIN avila.person p ON p.id = al.person_id
    WHERE al.invoice_id = ${id}::uuid
    ORDER BY coalesce(al.service_date, al.created_at) DESC
    LIMIT ${FACTURA_AUTH_LIMIT}
  `;

  const files = await db`
    SELECT id, file_label, extension, pages, rule_id, backup_path
    FROM avila.source_file WHERE invoice_id = ${id}::uuid
    ORDER BY backup_path, created_at
  `;

  const fileFilter = fileRaw;
  const docs = fileFilter
    ? await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, d.source_file_id
        FROM avila.document d
        WHERE d.invoice_id = ${id}::uuid
          AND d.source_file_id = ${fileFilter}::uuid
        ORDER BY d.page_index, d.document_type
      `
    : await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, d.source_file_id
        FROM avila.document d
        WHERE d.invoice_id = ${id}::uuid
        ORDER BY d.page_index, d.document_type
      `;

  const [docCountRow] = await db`
    SELECT count(*)::int AS n FROM avila.document WHERE invoice_id = ${id}::uuid
  `;

  const atenciones = await queryAtenciones({ medicoId: "", personId: "", invoiceId: id });

  const fileRows = files as FacturaSourceFile[];
  return {
    atenciones,
    invoice: invoice as FacturaInvoice,
    people: people as FacturaPerson[],
    authTotal,
    authLines: authLines as FacturaAuthLine[],
    files: fileRows,
    docs: docs as FacturaDoc[],
    docTotal: docCountRow?.n ?? 0,
    fileFilter,
    activeFile: fileRows.find((f) => f.id === fileFilter),
  };
}
