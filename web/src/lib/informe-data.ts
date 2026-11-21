import { sql } from "./db";
import { BI_RANGES, getBiData, getEtlData, type BiRange } from "./dashboard-data";
import { EMPTY_ESTUDIO_SUMMARY, getEstudioSummary } from "./estudio-data";
import { getClinicalSummary, type ClinicalSummary } from "./medico-data";

const EMPTY_CLINICAL: ClinicalSummary = {
  kpis: { medicos: 0, conMpps: 0, conEspecialidad: 0, atenciones: 0, completas: 0, openReviews: 0 },
  topEspecialidades: [],
  statuses: [],
};

const num = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const LIST_LIMIT = 10;

export type InformePersonRow = {
  id: string;
  name: string;
  identityNumber: string | null;
  invoices: number;
  usd: number;
};

export type InformeInvoiceRow = {
  id: string;
  invoiceNumber: string;
  account: string | null;
  accountCode: string | null;
  usd: number | null;
  issueDate: string | null;
};

export type InformeDocumentRow = {
  id: string;
  documentType: string;
  pageIndex: number | null;
  invoiceNumber: string | null;
  uploadStatus: string;
};

export type InformeReviewRow = {
  id: string;
  kind: string;
  createdAt: string | null;
  personName: string | null;
  identityNumber: string | null;
  invoiceNumber: string | null;
};

async function safe<T>(query: Promise<T>, fallback: T, failures: string[], name: string): Promise<T> {
  try {
    return await query;
  } catch {
    failures.push(name);
    return fallback;
  }
}

export type ContactGapField = "birth_date" | "phone" | "address";

export type ContactGapRow = {
  field: ContactGapField;
  code: string;
  n: number;
};

/** Live synthesis of BI fiscal + ETL quality + contact gaps + role/auth cohorts + sample lists. */
export async function getInformeData(range: BiRange) {
  const db = sql();
  const failures: string[] = [];
  const months = BI_RANGES.find((r) => r.id === range)?.months ?? 12;

  const [bi, etl, contactSummary, contactGaps, roleCohorts, topClients, topInvoices, invoicesNoTitular, clientsNoCi, failedDocs, openReviews] =
    await Promise.all([
    getBiData(range),
    getEtlData(),
    safe(
      db`
        SELECT
          count(*)::int AS persons,
          count(*) FILTER (WHERE coalesce(identity_number, '') <> '')::int AS with_ci,
          count(*) FILTER (WHERE coalesce(identity_number, '') = '')::int AS without_ci,
          count(*) FILTER (
            WHERE contact_gap <> '{}'::jsonb
              AND (
                (contact_gap ? 'birth_date' AND nullif(contact_gap->>'birth_date', 'filled') IS NOT NULL)
                OR (contact_gap ? 'phone' AND nullif(contact_gap->>'phone', 'filled') IS NOT NULL)
                OR (contact_gap ? 'address' AND nullif(contact_gap->>'address', 'filled') IS NOT NULL)
              )
          )::int AS with_any_gap,
          count(*) FILTER (
            WHERE contact_gap ? 'birth_date'
              AND nullif(contact_gap->>'birth_date', 'filled') IS NOT NULL
          )::int AS birth_date_gaps,
          count(*) FILTER (
            WHERE contact_gap ? 'phone'
              AND nullif(contact_gap->>'phone', 'filled') IS NOT NULL
          )::int AS phone_gaps,
          count(*) FILTER (
            WHERE contact_gap ? 'address'
              AND nullif(contact_gap->>'address', 'filled') IS NOT NULL
          )::int AS address_gaps
        FROM avila.person
      `,
      [
        {
          persons: 0,
          with_ci: 0,
          without_ci: 0,
          with_any_gap: 0,
          birth_date_gaps: 0,
          phone_gaps: 0,
          address_gaps: 0,
        },
      ],
      failures,
      "completitud de contacto",
    ),
    safe(
      db`
        SELECT field, code, count(*)::int AS n
        FROM (
          SELECT 'birth_date'::text AS field, contact_gap->>'birth_date' AS code
          FROM avila.person
          WHERE contact_gap ? 'birth_date'
            AND nullif(contact_gap->>'birth_date', 'filled') IS NOT NULL
          UNION ALL
          SELECT 'phone'::text, contact_gap->>'phone'
          FROM avila.person
          WHERE contact_gap ? 'phone'
            AND nullif(contact_gap->>'phone', 'filled') IS NOT NULL
          UNION ALL
          SELECT 'address'::text, contact_gap->>'address'
          FROM avila.person
          WHERE contact_gap ? 'address'
            AND nullif(contact_gap->>'address', 'filled') IS NOT NULL
        ) gaps
        GROUP BY field, code
        ORDER BY n DESC
        LIMIT 12
      `,
      [],
      failures,
      "códigos de contacto",
    ),
    safe(
      db`
        SELECT
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )
          )::int AS with_titular,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )
            AND EXISTS (
              SELECT 1 FROM avila.invoice_person bip
              WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
            )
          )::int AS titular_and_beneficiario,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM avila.invoice_person tip
              WHERE tip.invoice_id = i.id AND tip.role = 'titular'
            )
            AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_person bip
              WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario'
            )
          )::int AS titular_only,
          count(*) FILTER (WHERE i.role_cohort = 'mismatch_no_beneficiario')::int AS mismatch_no_beneficiario,
          count(*) FILTER (WHERE i.role_cohort = 'id_docs_no_ci')::int AS id_docs_no_ci,
          count(*) FILTER (WHERE i.role_cohort = 'nameless_titular')::int AS nameless_titular,
          count(*) FILTER (WHERE i.role_cohort = 'blocked_review')::int AS blocked_review,
          (SELECT count(*)::int FROM avila.invoice) AS invoices
        FROM avila.invoice i
      `,
      [
        {
          with_titular: 0,
          titular_and_beneficiario: 0,
          titular_only: 0,
          mismatch_no_beneficiario: 0,
          id_docs_no_ci: 0,
          nameless_titular: 0,
          blocked_review: 0,
          invoices: 0,
        },
      ],
      failures,
      "cohortes de rol",
    ),
    safe(
      db`
        SELECT p.id::text AS id,
               coalesce(nullif(trim(p.full_name), ''), '(sin nombre)') AS name,
               nullif(trim(p.identity_number), '') AS identity_number,
               count(DISTINCT i.id)::int AS invoices,
               coalesce(sum(i.total_usd), 0)::float8 AS usd
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        JOIN avila.invoice i ON i.id = ip.invoice_id
        WHERE ip.role = 'titular'
          AND i.issue_date IS NOT NULL
          AND (${months}::int = 0 OR i.issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
        GROUP BY p.id, p.full_name, p.identity_number
        ORDER BY usd DESC NULLS LAST, invoices DESC, name
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "clientes del periodo",
    ),
    safe(
      db`
        SELECT i.id::text AS id,
               i.invoice_number,
               a.legal_name AS account,
               a.code AS account_code,
               i.total_usd::float8 AS usd,
               i.issue_date::text AS issue_date
        FROM avila.invoice i
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE i.issue_date IS NOT NULL
          AND i.total_usd IS NOT NULL
          AND (${months}::int = 0 OR i.issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
        ORDER BY i.total_usd DESC, i.issue_date DESC
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "facturas del periodo",
    ),
    safe(
      db`
        SELECT i.id::text AS id,
               i.invoice_number,
               a.legal_name AS account,
               a.code AS account_code,
               i.total_usd::float8 AS usd,
               i.issue_date::text AS issue_date
        FROM avila.invoice i
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE NOT EXISTS (
          SELECT 1 FROM avila.invoice_person tip
          WHERE tip.invoice_id = i.id AND tip.role = 'titular'
        )
        ORDER BY i.issue_date DESC NULLS LAST, i.invoice_number DESC
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "facturas sin titular",
    ),
    safe(
      db`
        SELECT p.id::text AS id,
               coalesce(nullif(trim(p.full_name), ''), '(sin nombre)') AS name,
               nullif(trim(p.identity_number), '') AS identity_number,
               count(DISTINCT ip.invoice_id)::int AS invoices,
               0::float8 AS usd
        FROM avila.person p
        LEFT JOIN avila.invoice_person ip ON ip.person_id = p.id
        WHERE coalesce(p.identity_number, '') = ''
        GROUP BY p.id, p.full_name, p.identity_number
        ORDER BY invoices DESC, name
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "clientes sin cédula",
    ),
    safe(
      db`
        SELECT d.id::text AS id,
               d.document_type::text AS document_type,
               d.page_index,
               i.invoice_number,
               d.upload_status::text AS upload_status
        FROM avila.document d
        LEFT JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE d.upload_status = 'failed'
        ORDER BY d.created_at DESC
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "documentos fallidos",
    ),
    safe(
      db`
        SELECT r.id::text AS id,
               r.kind,
               r.created_at::text AS created_at,
               p.full_name AS person_name,
               p.identity_number,
               i.invoice_number
        FROM avila.review_item r
        LEFT JOIN avila.person p ON p.id = r.person_id
        LEFT JOIN avila.invoice i ON i.id = r.invoice_id
        WHERE r.status = 'open'
        ORDER BY r.score DESC NULLS LAST, r.created_at DESC
        LIMIT ${LIST_LIMIT}
      `,
      [],
      failures,
      "casos de revisión",
    ),
  ]);

  failures.push(...bi.failures, ...etl.failures);
  const clinical = await safe(getClinicalSummary(), EMPTY_CLINICAL, failures, "médicos y especialidades");
  const estudios = await safe(getEstudioSummary(), EMPTY_ESTUDIO_SUMMARY, failures, "estudios");

  const contact = contactSummary[0];
  const roles = roleCohorts[0];
  // Inventory linkage (all lines), not the period-dated BI funnel — avoids 0/0 when dates are sparse.
  const authLines = etl.kpi.authLines;
  const authLinked = etl.kpi.authLinked;

  return {
    failures: [...new Set(failures)],
    range: bi.range,
    months: bi.months,
    generatedAt: new Date().toISOString(),
    totals: bi.totals,
    previous: bi.previous,
    undated: bi.undated,
    monthly: bi.monthly,
    byAccount: bi.byAccount,
    byChannel: bi.byChannel,
    authorization: bi.authorization,
    providers: bi.providers,
    documentMix: bi.documentMix,
    counts: etl.counts,
    kpi: etl.kpi,
    clinical,
    estudios,
    reviews: etl.reviews,
    contact: {
      persons: num(contact.persons),
      withCi: num(contact.with_ci),
      withoutCi: num(contact.without_ci),
      withAnyGap: num(contact.with_any_gap),
      birthDateGaps: num(contact.birth_date_gaps),
      phoneGaps: num(contact.phone_gaps),
      addressGaps: num(contact.address_gaps),
      byCode: contactGaps.map(
        (r): ContactGapRow => ({
          field: String(r.field) as ContactGapField,
          code: String(r.code),
          n: num(r.n),
        }),
      ),
    },
    roles: {
      invoices: num(roles.invoices),
      withTitular: num(roles.with_titular),
      titularOnly: num(roles.titular_only),
      titularAndBeneficiario: num(roles.titular_and_beneficiario),
      noTitular: Math.max(0, num(roles.invoices) - num(roles.with_titular)),
      mismatchNoBeneficiario: num(roles.mismatch_no_beneficiario),
      idDocsNoCi: num(roles.id_docs_no_ci),
      namelessTitular: num(roles.nameless_titular),
      blockedReview: num(roles.blocked_review),
    },
    authLinkage: {
      lines: authLines,
      linked: authLinked,
      ratio: authLines > 0 ? authLinked / authLines : 0,
    },
    lists: {
      topClients: topClients.map(
        (r): InformePersonRow => ({
          id: String(r.id),
          name: String(r.name),
          identityNumber: r.identity_number ? String(r.identity_number) : null,
          invoices: num(r.invoices),
          usd: num(r.usd),
        }),
      ),
      topInvoices: topInvoices.map(
        (r): InformeInvoiceRow => ({
          id: String(r.id),
          invoiceNumber: String(r.invoice_number),
          account: r.account ? String(r.account) : null,
          accountCode: r.account_code ? String(r.account_code) : null,
          usd: r.usd == null ? null : num(r.usd),
          issueDate: r.issue_date ? String(r.issue_date).slice(0, 10) : null,
        }),
      ),
      invoicesNoTitular: invoicesNoTitular.map(
        (r): InformeInvoiceRow => ({
          id: String(r.id),
          invoiceNumber: String(r.invoice_number),
          account: r.account ? String(r.account) : null,
          accountCode: r.account_code ? String(r.account_code) : null,
          usd: r.usd == null ? null : num(r.usd),
          issueDate: r.issue_date ? String(r.issue_date).slice(0, 10) : null,
        }),
      ),
      clientsNoCi: clientsNoCi.map(
        (r): InformePersonRow => ({
          id: String(r.id),
          name: String(r.name),
          identityNumber: null,
          invoices: num(r.invoices),
          usd: 0,
        }),
      ),
      failedDocuments: failedDocs.map(
        (r): InformeDocumentRow => ({
          id: String(r.id),
          documentType: String(r.document_type),
          pageIndex: r.page_index == null ? null : num(r.page_index),
          invoiceNumber: r.invoice_number ? String(r.invoice_number) : null,
          uploadStatus: String(r.upload_status),
        }),
      ),
      openReviews: openReviews.map(
        (r): InformeReviewRow => ({
          id: String(r.id),
          kind: String(r.kind),
          createdAt: r.created_at ? String(r.created_at) : null,
          personName: r.person_name ? String(r.person_name) : null,
          identityNumber: r.identity_number ? String(r.identity_number) : null,
          invoiceNumber: r.invoice_number ? String(r.invoice_number) : null,
        }),
      ),
    },
  };
}

export type InformeData = Awaited<ReturnType<typeof getInformeData>>;
