import { sql } from "@/lib/db";

export type FacturaListRow = {
  id: string;
  invoice_number: string | null;
  year: string | null;
  month: string | null;
  lote: string | null;
  account: string | null;
  docs: number;
  has_person: number;
  has_titular: number;
};

/** URL role_gap values → avila.invoice.role_cohort (sql/010). */
export const ROLE_GAP_COHORTS: Record<string, string> = {
  mismatch: "mismatch_no_beneficiario",
  no_ci: "id_docs_no_ci",
  nameless: "nameless_titular",
  blocked: "blocked_review",
  multi: "multi_titular",
};

export type FacturaListFilters = {
  query: string;
  like: string;
  account: string;
  year: string;
  month: string;
  hasPerson: string;
  hasTitular: string;
  hasDocs: string;
  roleGap?: string;
  pageSize: number;
  requestedPage: number;
  exportLimit: number;
};

export async function queryFacturaList(filters: FacturaListFilters): Promise<{
  total: number;
  page: number;
  pageRows: FacturaListRow[];
  exportRows: FacturaListRow[];
}> {
  const {
    query,
    like,
    account,
    year,
    month,
    hasPerson,
    hasTitular,
    hasDocs,
    roleGap = "",
    pageSize,
    requestedPage,
    exportLimit,
  } = filters;
  const roleCohort = ROLE_GAP_COHORTS[roleGap] ?? "";
  const db = sql();

  const [countRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${query} = '' OR i.invoice_number ILIKE ${like})
      AND (${account} = '' OR a.code = ${account})
      AND (${year} = '' OR i.year = ${year})
      AND (${month} = '' OR i.month = ${month})
      AND (${hasPerson} = '' OR (${hasPerson} = '1' AND EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )) OR (${hasPerson} = '0' AND NOT EXISTS (
            SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
          )))
      AND (${hasTitular} = '' OR (${hasTitular} = '1' AND EXISTS (
            SELECT 1 FROM avila.invoice_person tip
            WHERE tip.invoice_id = i.id AND tip.role = 'titular'
          )) OR (${hasTitular} = '0' AND NOT EXISTS (
            SELECT 1 FROM avila.invoice_person tip
            WHERE tip.invoice_id = i.id AND tip.role = 'titular'
          )))
      AND (${hasDocs} = '' OR (${hasDocs} = '1' AND EXISTS (
            SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
          )) OR (${hasDocs} = '0' AND NOT EXISTS (
            SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
          )))
      AND (${roleCohort} = '' OR i.role_cohort = ${roleCohort})
  `;

  const total = countRow?.n ?? 0;
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  const offset = (page - 1) * pageSize;

  const [pageRows, exportRows] = await Promise.all([
    db`
      SELECT i.id, i.invoice_number, i.year, i.month, i.lote, a.legal_name AS account,
             coalesce(dc.docs, 0)::int AS docs,
             CASE WHEN EXISTS (
               SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
             ) THEN 1 ELSE 0 END::int AS has_person,
             CASE WHEN EXISTS (
               SELECT 1 FROM avila.invoice_person tip
               WHERE tip.invoice_id = i.id AND tip.role = 'titular'
             ) THEN 1 ELSE 0 END::int AS has_titular
      FROM avila.invoice i
      LEFT JOIN avila.account a ON a.id = i.account_id
      LEFT JOIN (
        SELECT invoice_id, count(*)::int AS docs FROM avila.document GROUP BY invoice_id
      ) dc ON dc.invoice_id = i.id
      WHERE (${query} = '' OR i.invoice_number ILIKE ${like})
        AND (${account} = '' OR a.code = ${account})
        AND (${year} = '' OR i.year = ${year})
        AND (${month} = '' OR i.month = ${month})
        AND (${hasPerson} = '' OR (${hasPerson} = '1' AND EXISTS (
              SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
            )) OR (${hasPerson} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
            )))
        AND (${hasTitular} = '' OR (${hasTitular} = '1' AND EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )) OR (${hasTitular} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )))
        AND (${hasDocs} = '' OR (${hasDocs} = '1' AND EXISTS (
              SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
            )) OR (${hasDocs} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
            )))
        AND (${roleCohort} = '' OR i.role_cohort = ${roleCohort})
      ORDER BY i.invoice_number DESC
      LIMIT ${pageSize} OFFSET ${offset}
    `,
    db`
      SELECT i.id, i.invoice_number, i.year, i.month, i.lote, a.legal_name AS account,
             coalesce(dc.docs, 0)::int AS docs,
             CASE WHEN EXISTS (
               SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
             ) THEN 1 ELSE 0 END::int AS has_person,
             CASE WHEN EXISTS (
               SELECT 1 FROM avila.invoice_person tip
               WHERE tip.invoice_id = i.id AND tip.role = 'titular'
             ) THEN 1 ELSE 0 END::int AS has_titular
      FROM avila.invoice i
      LEFT JOIN avila.account a ON a.id = i.account_id
      LEFT JOIN (
        SELECT invoice_id, count(*)::int AS docs FROM avila.document GROUP BY invoice_id
      ) dc ON dc.invoice_id = i.id
      WHERE (${query} = '' OR i.invoice_number ILIKE ${like})
        AND (${account} = '' OR a.code = ${account})
        AND (${year} = '' OR i.year = ${year})
        AND (${month} = '' OR i.month = ${month})
        AND (${hasPerson} = '' OR (${hasPerson} = '1' AND EXISTS (
              SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
            )) OR (${hasPerson} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
            )))
        AND (${hasTitular} = '' OR (${hasTitular} = '1' AND EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )) OR (${hasTitular} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )))
        AND (${hasDocs} = '' OR (${hasDocs} = '1' AND EXISTS (
              SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
            )) OR (${hasDocs} = '0' AND NOT EXISTS (
              SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
            )))
        AND (${roleCohort} = '' OR i.role_cohort = ${roleCohort})
      ORDER BY i.invoice_number DESC
      LIMIT ${exportLimit}
    `,
  ]);

  return {
    total,
    page,
    pageRows: pageRows as FacturaListRow[],
    exportRows: exportRows as FacturaListRow[],
  };
}
