import { sql } from "@/lib/db";

export type DocumentAccountOption = { code: string; legal_name: string };
export type DocumentTypeCount = { document_type: string; n: number };
export type DocumentStatusCount = { upload_status: string; n: number };
export type DocumentListRow = {
  id: string;
  page_index: number | null;
  document_type: string;
  upload_status: string;
  invoice_number: string | null;
};

export type DocumentoList = {
  accounts: DocumentAccountOption[];
  types: DocumentTypeCount[];
  statusCounts: DocumentStatusCount[];
  total: number;
  page: number;
  docs: DocumentListRow[];
};

export async function queryDocumentoList(input: {
  typeOk: string;
  statusOk: string;
  account: string;
  query: string;
  pageSize: number;
  requestedPage: number;
}): Promise<DocumentoList> {
  const { typeOk, statusOk, account, query, pageSize, requestedPage } = input;
  const like = `%${query}%`;
  const db = sql();

  const [accounts, types, statusCounts, countRows] = await Promise.all([
    db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`,
    db`
      SELECT document_type::text AS document_type, count(*)::int AS n
      FROM avila.document GROUP BY 1 ORDER BY n DESC
    `,
    db`
      SELECT upload_status::text AS upload_status, count(*)::int AS n
      FROM avila.document GROUP BY 1 ORDER BY n DESC
    `,
    db`
      SELECT count(*)::int AS n
      FROM avila.document d
      LEFT JOIN avila.invoice i ON i.id = d.invoice_id
      LEFT JOIN avila.account a ON a.id = i.account_id
      WHERE (${typeOk} = '' OR d.document_type::text = ${typeOk})
        AND (${statusOk} = '' OR d.upload_status::text = ${statusOk})
        AND (${account} = '' OR a.code = ${account})
        AND (${query} = '' OR coalesce(i.invoice_number, '') ILIKE ${like}
             OR coalesce(d.evidence, '') ILIKE ${like})
    `,
  ]);

  const total = (countRows[0] as { n: number } | undefined)?.n ?? 0;
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  const offset = (page - 1) * pageSize;

  const docs = await db`
    SELECT d.id, d.page_index, d.document_type::text AS document_type,
           d.upload_status::text AS upload_status, i.invoice_number
    FROM avila.document d
    LEFT JOIN avila.invoice i ON i.id = d.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${typeOk} = '' OR d.document_type::text = ${typeOk})
      AND (${statusOk} = '' OR d.upload_status::text = ${statusOk})
      AND (${account} = '' OR a.code = ${account})
      AND (${query} = '' OR coalesce(i.invoice_number, '') ILIKE ${like}
           OR coalesce(d.evidence, '') ILIKE ${like})
    ORDER BY d.created_at DESC
    LIMIT ${pageSize} OFFSET ${offset}
  `;

  return {
    accounts: accounts as DocumentAccountOption[],
    types: types as DocumentTypeCount[],
    statusCounts: statusCounts as DocumentStatusCount[],
    total,
    page,
    docs: docs as DocumentListRow[],
  };
}

export type DocumentoRecord = {
  id: string;
  page_index: number | null;
  document_type: string;
  evidence: string | null;
  upload_status: string;
  upload_error: string | null;
  blob_url: string | null;
  blob_pathname: string | null;
  invoice_id: string | null;
  person_id: string | null;
  source_file_id: string | null;
  invoice_number: string | null;
  identity_number: string | null;
  full_name: string | null;
  file_label: string | null;
  extension: string | null;
  source_pages: number | null;
  rule_id: string | null;
  backup_path: string | null;
};

export type DocumentoSibling = {
  id: string;
  page_index: number | null;
  document_type: string;
  upload_status: string;
};

export type DocumentoInvoicePerson = {
  id: string;
  full_name: string | null;
  identity_number: string | null;
  role: string;
};

export type DocumentoDetail = {
  doc: DocumentoRecord;
  siblings: DocumentoSibling[];
  invoicePeople: DocumentoInvoicePerson[];
};

export async function getDocumentoDetail(id: string): Promise<DocumentoDetail | null> {
  const db = sql();
  const [doc] = await db`
    SELECT d.id, d.page_index, d.document_type::text AS document_type, d.evidence,
           d.upload_status::text AS upload_status, d.upload_error, d.blob_url, d.blob_pathname,
           d.invoice_id, d.person_id, d.source_file_id,
           i.invoice_number,
           p.identity_number, p.full_name,
           sf.file_label, sf.extension, sf.pages AS source_pages, sf.rule_id,
           sf.backup_path
    FROM avila.document d
    LEFT JOIN avila.invoice i ON i.id = d.invoice_id
    LEFT JOIN avila.person p ON p.id = d.person_id
    LEFT JOIN avila.source_file sf ON sf.id = d.source_file_id
    WHERE d.id = ${id}::uuid
  `;
  if (!doc) return null;
  const record = doc as DocumentoRecord;

  const siblings = record.source_file_id
    ? await db`
        SELECT id, page_index, document_type::text AS document_type,
               upload_status::text AS upload_status
        FROM avila.document
        WHERE source_file_id = ${record.source_file_id}::uuid
        ORDER BY page_index
      `
    : [];

  const invoicePeople = record.invoice_id
    ? await db`
        SELECT p.id, p.full_name, p.identity_number, ip.role::text AS role
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = ${record.invoice_id}::uuid
        ORDER BY CASE ip.role
          WHEN 'titular' THEN 0
          WHEN 'beneficiario' THEN 1
          ELSE 2
        END, p.full_name
      `
    : [];

  return {
    doc: record,
    siblings: siblings as DocumentoSibling[],
    invoicePeople: invoicePeople as DocumentoInvoicePerson[],
  };
}
