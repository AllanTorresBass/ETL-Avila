import { sql } from "./db";

export type BiRange = "6m" | "12m" | "24m" | "todo";

export const BI_RANGES: { id: BiRange; label: string; months: number }[] = [
  { id: "6m", label: "6 meses", months: 6 },
  { id: "12m", label: "12 meses", months: 12 },
  { id: "24m", label: "24 meses", months: 24 },
  { id: "todo", label: "Todo", months: 0 },
];

export function parseRange(value: string | string[] | undefined): BiRange {
  const raw = Array.isArray(value) ? value[0] : value;
  return BI_RANGES.some((r) => r.id === raw) ? (raw as BiRange) : "12m";
}

const num = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

/** A failed query degrades only its own panel instead of taking the dashboard down. */
async function safe<T>(query: Promise<T>, fallback: T, failures: string[], name: string): Promise<T> {
  try {
    return await query;
  } catch {
    failures.push(name);
    return fallback;
  }
}

export type EtlRun = {
  id: string;
  script: string;
  mode: "dry" | "apply";
  startedAt: string;
  finishedAt: string | null;
  counters: Record<string, unknown>;
};

export async function getEtlData() {
  const db = sql();
  const failures: string[] = [];

  const [counts, kpi, byType, uploads, reviews, runs, provenance] = await Promise.all([
    safe(
      db`
        SELECT
          (SELECT count(*)::int FROM avila.person) AS persons,
          (SELECT count(*)::int FROM avila.invoice) AS invoices,
          (SELECT count(*)::int FROM avila.source_file) AS source_files,
          (SELECT count(*)::int FROM avila.document) AS documents,
          (SELECT count(*)::int FROM avila.document WHERE upload_status = 'uploaded') AS uploaded,
          (SELECT count(*)::int FROM avila.document WHERE upload_status = 'failed') AS failed
      `,
      [{ persons: 0, invoices: 0, source_files: 0, documents: 0, uploaded: 0, failed: 0 }],
      failures,
      "inventario",
    ),
    safe(
      db`
        SELECT
          (SELECT count(*)::int FROM avila.authorization_line) AS auth_lines,
          (SELECT count(*)::int FROM avila.authorization_line WHERE invoice_id IS NOT NULL) AS auth_linked,
          (SELECT count(DISTINCT ip.invoice_id)::int
             FROM avila.invoice_person ip JOIN avila.person p ON p.id = ip.person_id
             WHERE ip.role = 'titular' AND p.identity_type = 'cedula') AS invoices_ci_titular,
          (SELECT count(*)::int FROM avila.person p
             WHERE NOT EXISTS (SELECT 1 FROM avila.invoice_person ip WHERE ip.person_id = p.id)) AS persons_no_invoice,
          (SELECT count(*)::int FROM avila.review_item WHERE status = 'open') AS open_reviews,
          (SELECT count(*)::int FROM avila.source_file WHERE rule_id = 'scan_packet') AS scan_files,
          (SELECT count(*)::int FROM avila.invoice i
             WHERE NOT EXISTS (
               SELECT 1 FROM avila.invoice_person tip WHERE tip.invoice_id = i.id AND tip.role = 'titular'
             )) AS invoices_no_titular,
          (SELECT count(*)::int FROM avila.invoice i
             WHERE EXISTS (SELECT 1 FROM avila.invoice_person tip WHERE tip.invoice_id = i.id AND tip.role = 'titular')
               AND EXISTS (SELECT 1 FROM avila.invoice_person bip WHERE bip.invoice_id = i.id AND bip.role = 'beneficiario')
          ) AS invoices_with_beneficiario,
          (SELECT count(*)::int FROM avila.review_item
             WHERE status = 'open' AND kind IN ('ci_conflict', 'multiple_ci', 'workbook_titular', 'acta_titular')) AS open_role_reviews,
          (SELECT count(*)::int FROM avila.invoice WHERE role_cohort = 'mismatch_no_beneficiario') AS mismatch_no_beneficiario,
          (SELECT count(*)::int FROM avila.invoice WHERE role_cohort = 'id_docs_no_ci') AS id_docs_no_ci,
          (SELECT count(*)::int FROM avila.invoice WHERE role_cohort = 'nameless_titular') AS nameless_titular,
          (SELECT count(*)::int FROM avila.invoice WHERE role_cohort = 'blocked_review') AS blocked_review_cohort,
          (SELECT count(*)::int FROM avila.invoice WHERE role_cohort = 'multi_titular') AS multi_titular
      `,
      [
        {
          auth_lines: 0,
          auth_linked: 0,
          invoices_ci_titular: 0,
          persons_no_invoice: 0,
          open_reviews: 0,
          scan_files: 0,
          invoices_no_titular: 0,
          invoices_with_beneficiario: 0,
          open_role_reviews: 0,
          mismatch_no_beneficiario: 0,
          id_docs_no_ci: 0,
          nameless_titular: 0,
          blocked_review_cohort: 0,
          multi_titular: 0,
        },
      ],
      failures,
      "calidad",
    ),
    safe(
      db`SELECT document_type::text AS document_type, count(*)::int AS n FROM avila.document GROUP BY 1 ORDER BY n DESC`,
      [],
      failures,
      "tipos de documento",
    ),
    safe(
      db`SELECT upload_status::text AS status, count(*)::int AS n FROM avila.document GROUP BY 1`,
      [],
      failures,
      "estado de carga",
    ),
    safe(
      db`
        SELECT kind, status, count(*)::int AS n
        FROM avila.review_item
        GROUP BY kind, status
      `,
      [],
      failures,
      "cola de revisión",
    ),
    safe(
      db`
        SELECT id::text AS id, script, mode, started_at, finished_at, counters
        FROM avila.etl_run
        ORDER BY started_at DESC
        LIMIT 8
      `,
      [],
      failures,
      "ejecuciones",
    ),
    safe(
      db`
        SELECT source_kind, count(*)::int AS n, avg(confidence)::float8 AS avg_confidence
        FROM avila.field_provenance
        GROUP BY source_kind
        ORDER BY n DESC
      `,
      [],
      failures,
      "procedencia",
    ),
  ]);

  const c = counts[0];
  const k = kpi[0];

  return {
    failures,
    counts: {
      persons: num(c.persons),
      invoices: num(c.invoices),
      sourceFiles: num(c.source_files),
      documents: num(c.documents),
      uploaded: num(c.uploaded),
      failed: num(c.failed),
    },
    kpi: {
      authLines: num(k.auth_lines),
      authLinked: num(k.auth_linked),
      invoicesCiTitular: num(k.invoices_ci_titular),
      personsNoInvoice: num(k.persons_no_invoice),
      openReviews: num(k.open_reviews),
      scanFiles: num(k.scan_files),
      invoicesNoTitular: num(k.invoices_no_titular),
      invoicesWithBeneficiario: num(k.invoices_with_beneficiario),
      openRoleReviews: num(k.open_role_reviews),
      mismatchNoBeneficiario: num(k.mismatch_no_beneficiario),
      idDocsNoCi: num(k.id_docs_no_ci),
      namelessTitular: num(k.nameless_titular),
      blockedReviewCohort: num(k.blocked_review_cohort),
      multiTitular: num(k.multi_titular),
    },
    byType: byType.map((r) => ({ key: String(r.document_type), n: num(r.n) })),
    uploads: uploads.map((r) => ({ status: String(r.status), n: num(r.n) })),
    reviews: reviews.map((r) => ({ kind: String(r.kind), status: String(r.status), n: num(r.n) })),
    runs: runs.map(
      (r): EtlRun => ({
        id: String(r.id),
        script: String(r.script),
        mode: r.mode === "apply" ? "apply" : "dry",
        startedAt: new Date(r.started_at).toISOString(),
        finishedAt: r.finished_at ? new Date(r.finished_at).toISOString() : null,
        counters: (r.counters ?? {}) as Record<string, unknown>,
      }),
    ),
    provenance: provenance.map((r) => ({
      sourceKind: String(r.source_kind),
      n: num(r.n),
      avgConfidence: r.avg_confidence == null ? null : num(r.avg_confidence),
    })),
  };
}

export type MonthPoint = { month: string; usd: number; invoices: number };

/** Fill months without invoices so the trend line is continuous. */
function fillMonths(points: MonthPoint[]): MonthPoint[] {
  if (points.length < 2) return points;
  const byMonth = new Map(points.map((p) => [p.month, p]));
  const [startYear, startMonth] = points[0].month.split("-").map(Number);
  const [endYear, endMonth] = points[points.length - 1].month.split("-").map(Number);
  const filled: MonthPoint[] = [];
  let year = startYear;
  let month = startMonth;
  while (year < endYear || (year === endYear && month <= endMonth)) {
    const key = `${year}-${String(month).padStart(2, "0")}`;
    filled.push(byMonth.get(key) ?? { month: key, usd: 0, invoices: 0 });
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return filled;
}

export async function getBiData(range: BiRange) {
  const db = sql();
  const failures: string[] = [];
  const months = BI_RANGES.find((r) => r.id === range)?.months ?? 12;

  const [totals, previous, monthly, byAccount, byChannel, authorization, providers, undated, documentMix] =
    await Promise.all([
      safe(
        db`
          SELECT
            count(*)::int AS invoices,
            count(total_usd)::int AS with_usd,
            coalesce(sum(total_usd), 0)::float8 AS usd,
            coalesce(sum(total_bs), 0)::float8 AS bs,
            coalesce(max(total_usd), 0)::float8 AS max_usd
          FROM avila.invoice
          WHERE issue_date IS NOT NULL
            AND (${months}::int = 0 OR issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
        `,
        [{ invoices: 0, with_usd: 0, usd: 0, bs: 0, max_usd: 0 }],
        failures,
        "totales",
      ),
      safe(
        db`
          SELECT count(*)::int AS invoices, coalesce(sum(total_usd), 0)::float8 AS usd
          FROM avila.invoice
          WHERE ${months}::int > 0
            AND issue_date IS NOT NULL
            AND issue_date < (date_trunc('month', now()) - make_interval(months => ${months}::int))::date
            AND issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int * 2))::date
        `,
        [{ invoices: 0, usd: 0 }],
        failures,
        "periodo anterior",
      ),
      safe(
        db`
          SELECT to_char(date_trunc('month', issue_date), 'YYYY-MM') AS month,
                 count(*)::int AS invoices,
                 coalesce(sum(total_usd), 0)::float8 AS usd
          FROM avila.invoice
          WHERE issue_date IS NOT NULL
            AND (${months}::int = 0 OR issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
          GROUP BY 1
          ORDER BY 1
        `,
        [],
        failures,
        "tendencia",
      ),
      safe(
        db`
          SELECT a.code AS code, coalesce(a.legal_name, '(sin cuenta)') AS name,
                 count(*)::int AS invoices,
                 coalesce(sum(i.total_usd), 0)::float8 AS usd
          FROM avila.invoice i
          LEFT JOIN avila.account a ON a.id = i.account_id
          WHERE i.issue_date IS NOT NULL
            AND (${months}::int = 0 OR i.issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
          GROUP BY a.code, a.legal_name
          ORDER BY usd DESC, invoices DESC
          LIMIT 8
        `,
        [],
        failures,
        "cuentas",
      ),
      safe(
        db`
          SELECT coalesce(nullif(trim(channel), ''), '(sin canal)') AS channel,
                 count(*)::int AS invoices,
                 coalesce(sum(total_usd), 0)::float8 AS usd
          FROM avila.invoice
          WHERE issue_date IS NOT NULL
            AND (${months}::int = 0 OR issue_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
          GROUP BY 1
          ORDER BY invoices DESC
          LIMIT 6
        `,
        [],
        failures,
        "canales",
      ),
      safe(
        db`
          SELECT
            count(*)::int AS lines,
            count(invoice_id)::int AS linked,
            coalesce(sum(amount_usd), 0)::float8 AS requested_usd,
            coalesce(sum(authorized_amount), 0)::float8 AS authorized,
            coalesce(sum(coverage_amount), 0)::float8 AS coverage
          FROM avila.authorization_line
          WHERE request_date IS NOT NULL
            AND (${months}::int = 0 OR request_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
        `,
        [{ lines: 0, linked: 0, requested_usd: 0, authorized: 0, coverage: 0 }],
        failures,
        "autorizaciones",
      ),
      safe(
        db`
          SELECT coalesce(nullif(trim(provider_name), ''), '(sin proveedor)') AS provider,
                 count(*)::int AS lines,
                 coalesce(sum(amount_usd), 0)::float8 AS usd
          FROM avila.authorization_line
          WHERE request_date IS NOT NULL
            AND (${months}::int = 0 OR request_date >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
          GROUP BY 1
          ORDER BY usd DESC, lines DESC
          LIMIT 6
        `,
        [],
        failures,
        "proveedores",
      ),
      safe(
        db`SELECT count(*)::int AS n FROM avila.invoice WHERE issue_date IS NULL`,
        [{ n: 0 }],
        failures,
        "sin fecha",
      ),
      safe(
        db`SELECT document_type::text AS document_type, count(*)::int AS n FROM avila.document GROUP BY 1 ORDER BY n DESC`,
        [],
        failures,
        "documentos",
      ),
    ]);

  const t = totals[0];
  const p = previous[0];
  const a = authorization[0];

  const invoices = num(t.invoices);
  const withUsd = num(t.with_usd);
  const usd = num(t.usd);

  return {
    failures,
    range,
    months,
    totals: {
      invoices,
      withUsd,
      usd,
      bs: num(t.bs),
      maxUsd: num(t.max_usd),
      averageUsd: withUsd > 0 ? usd / withUsd : 0,
      usdCoverage: invoices > 0 ? withUsd / invoices : 0,
    },
    previous: { invoices: num(p.invoices), usd: num(p.usd) },
    undated: num(undated[0].n),
    monthly: fillMonths(
      monthly.map((r) => ({ month: String(r.month), usd: num(r.usd), invoices: num(r.invoices) })),
    ),
    byAccount: byAccount.map((r) => ({
      code: r.code ? String(r.code) : null,
      name: String(r.name),
      invoices: num(r.invoices),
      usd: num(r.usd),
    })),
    byChannel: byChannel.map((r) => ({
      channel: String(r.channel),
      invoices: num(r.invoices),
      usd: num(r.usd),
    })),
    authorization: {
      lines: num(a.lines),
      linked: num(a.linked),
      requestedUsd: num(a.requested_usd),
      authorized: num(a.authorized),
      coverage: num(a.coverage),
    },
    providers: providers.map((r) => ({
      provider: String(r.provider),
      lines: num(r.lines),
      usd: num(r.usd),
    })),
    documentMix: documentMix.map((r) => ({ key: String(r.document_type), n: num(r.n) })),
  };
}
