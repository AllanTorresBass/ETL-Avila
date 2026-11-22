import { cache } from "react";
import { fillMonths } from "@/lib/dashboard-data";
import { sql } from "@/lib/db";
import { valueHash } from "@/lib/review-resolve";

export const AUTH_CANDIDATE_LIMIT = 20;
export const AUTH_HISTORY_LIMIT = 100;

export type AuthorizationListRow = {
  id: string;
  clave_rms: string | null;
  aps_code: string | null;
  request_date: string | Date | null;
  service_date: string | Date | null;
  period_month: string | Date | null;
  date_source: string | null;
  diagnosis: string | null;
  service_description: string | null;
  contratante: string | null;
  provider_name: string | null;
  amount_bs: string | number | null;
  amount_usd: string | number | null;
  match_status: string | null;
  match_score: number | null;
  person_id: string | null;
  person_name: string | null;
  titular_id: string | null;
  titular_name: string | null;
  invoice_id: string | null;
  invoice_number: string | null;
  account_name: string | null;
  especialidad: string | null;
  items: unknown;
};

export type AuthorizationListFilters = {
  query: string;
  like: string;
  aseguradora: string;
  contratante: string;
  estado: string;
  fecha: string;
  especialidad: string;
  desde: string;
  hasta: string;
  pageSize: number;
  requestedPage: number;
};

export async function queryAuthorizationList(filters: AuthorizationListFilters): Promise<{
  total: number;
  page: number;
  rows: AuthorizationListRow[];
}> {
  const { query, like, aseguradora, contratante, estado, fecha, especialidad, desde, hasta, pageSize, requestedPage } =
    filters;
  const db = sql();
  const result = await db`
    WITH f AS (
      SELECT al.*, coalesce(al.request_date, al.service_date, al.period_month) AS eff_date
      FROM avila.authorization_line al
      LEFT JOIN avila.account a ON a.id = al.account_id
      LEFT JOIN avila.person p ON p.id = al.person_id
      LEFT JOIN avila.person t ON t.id = al.titular_person_id
      LEFT JOIN avila.especialidad e ON e.id = al.especialidad_id
      LEFT JOIN avila.especialidad pe ON pe.id = e.parent_id
      WHERE al.duplicate_of IS NULL
        AND (${query} = ''
          OR coalesce(al.clave_rms, '') ILIKE ${like}
          OR coalesce(al.aps_code, '') ILIKE ${like}
          OR coalesce(al.diagnosis, '') ILIKE ${like}
          OR coalesce(p.full_name, '') ILIKE ${like}
          OR coalesce(p.identity_number, '') ILIKE ${like}
          OR coalesce(t.full_name, '') ILIKE ${like}
          OR coalesce(t.identity_number, '') ILIKE ${like})
        AND (${aseguradora} = '' OR a.code = ${aseguradora})
        AND (${contratante} = '' OR al.contratante = ${contratante})
        AND (${especialidad} = '' OR e.code = ${especialidad} OR pe.code = ${especialidad})
        AND (${estado} = ''
          OR (${estado} = 'vinculada' AND al.invoice_id IS NOT NULL)
          OR (${estado} = 'pendiente' AND al.invoice_id IS NULL)
          OR (${estado} = 'revision' AND al.invoice_id IS NULL AND EXISTS (
                SELECT 1 FROM avila.review_item r
                WHERE r.authorization_line_id = al.id AND r.kind = 'auth_match' AND r.status = 'open'))
          OR (${estado} IN ('low_score', 'no_candidate', 'no_person', 'staff') AND al.match_status = ${estado}))
        AND (${fecha} = ''
          OR (${fecha} = 'exacta' AND coalesce(al.request_date, al.service_date) IS NOT NULL)
          OR (${fecha} = 'periodo' AND al.request_date IS NULL AND al.service_date IS NULL AND al.period_month IS NOT NULL)
          OR (${fecha} = 'sin' AND al.request_date IS NULL AND al.service_date IS NULL AND al.period_month IS NULL))
        AND (${desde} = '' OR coalesce(al.request_date, al.service_date, al.period_month) >= nullif(${desde}, '')::date)
        AND (${hasta} = '' OR coalesce(al.request_date, al.service_date, al.period_month) <= nullif(${hasta}, '')::date)
    ),
    pg AS (
      SELECT n.total,
             least(greatest(1, ${requestedPage}::int), greatest(1, ceil(n.total / ${pageSize}::numeric)::int)) AS page
      FROM (SELECT count(*)::int AS total FROM f) n
    )
    SELECT pg.total, pg.page,
           r.id::text AS id, r.clave_rms, r.aps_code, r.request_date, r.service_date, r.period_month,
           r.date_source, r.diagnosis, r.service_description, r.contratante, r.provider_name,
           r.amount_bs, r.amount_usd, r.match_status, r.match_score::float8 AS match_score,
           r.person_id::text AS person_id, p.full_name AS person_name,
           r.titular_person_id::text AS titular_id, t.full_name AS titular_name,
           r.invoice_id::text AS invoice_id, i.invoice_number,
           a.legal_name AS account_name, e.name_es AS especialidad,
           coalesce((
             SELECT json_agg(json_build_object('label', ai.label, 'quantity', ai.quantity) ORDER BY ai.position)
             FROM avila.authorization_item ai WHERE ai.authorization_line_id = r.id
           ), '[]'::json) AS items
    FROM pg
    LEFT JOIN LATERAL (
      SELECT * FROM f
      ORDER BY f.eff_date DESC NULLS LAST, f.created_at DESC, f.id
      LIMIT ${pageSize} OFFSET (pg.page - 1) * ${pageSize}
    ) r ON true
    LEFT JOIN avila.person p ON p.id = r.person_id
    LEFT JOIN avila.person t ON t.id = r.titular_person_id
    LEFT JOIN avila.invoice i ON i.id = r.invoice_id
    LEFT JOIN avila.account a ON a.id = r.account_id
    LEFT JOIN avila.especialidad e ON e.id = r.especialidad_id
    ORDER BY r.eff_date DESC NULLS LAST, r.created_at DESC, r.id
  `;
  const head = result[0];
  return {
    total: Number(head?.total ?? 0),
    page: Number(head?.page ?? 1),
    rows: result.filter((r) => r.id) as AuthorizationListRow[],
  };
}

/** Corpus KPIs for /autorizaciones (duplicates excluded). */
export const getAuthorizationKpis = cache(async function getAuthorizationKpis() {
  const db = sql();
  const [row] = await db`
    SELECT
      count(*)::int AS lines,
      count(invoice_id)::int AS linked,
      count(*) FILTER (WHERE invoice_id IS NULL AND match_status IN ('review', 'low_score'))::int AS actionable,
      count(*) FILTER (WHERE request_date IS NULL AND service_date IS NULL)::int AS no_exact_date,
      count(*) FILTER (WHERE request_date IS NULL AND service_date IS NULL AND period_month IS NULL)::int AS no_date,
      coalesce(sum(amount_usd), 0)::float8 AS requested_usd,
      coalesce(sum(coverage_amount), 0)::float8 AS covered
    FROM avila.authorization_line
    WHERE duplicate_of IS NULL
  `;
  const [reviews] = await db`
    SELECT count(DISTINCT r.authorization_line_id)::int AS n
    FROM avila.review_item r
    JOIN avila.authorization_line al ON al.id = r.authorization_line_id
    WHERE r.kind = 'auth_match' AND r.status = 'open' AND al.invoice_id IS NULL AND al.duplicate_of IS NULL
  `;
  return {
    lines: row?.lines ?? 0,
    linked: row?.linked ?? 0,
    actionable: row?.actionable ?? 0,
    inReview: reviews?.n ?? 0,
    noExactDate: row?.no_exact_date ?? 0,
    noDate: row?.no_date ?? 0,
    requestedUsd: Number(row?.requested_usd ?? 0),
    covered: Number(row?.covered ?? 0),
  };
});

export type AuthorizationKpis = Awaited<ReturnType<typeof getAuthorizationKpis>>;

export type AuthGroupRow = { key: string; label: string; lines: number; linked: number; usd: number };
export type AuthTrendPoint = { month: string; usd: number; invoices: number };
export type AuthCountRow = { key: string; n: number };

/** Funnel, insurer, contratante, especialidad, trend, timing, and reasons. `months = 0` is all time. */
export async function getAuthorizationAnalytics(months: number) {
  const db = sql();
  const [funnel, insurers, contratantes, especialidades, trend, lag, statuses, dateSources] = await Promise.all([
    db`
      SELECT count(*)::int AS lines,
             count(*) FILTER (WHERE person_id IS NOT NULL OR titular_person_id IS NOT NULL)::int AS with_person,
             count(*) FILTER (WHERE coalesce(request_date, service_date, period_month) IS NOT NULL)::int AS with_date,
             count(*) FILTER (WHERE coalesce(request_date, service_date) IS NOT NULL)::int AS with_exact_date,
             count(invoice_id)::int AS linked
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL
        AND (${months}::int = 0 OR coalesce(request_date, service_date, period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
    `,
    db`
      SELECT coalesce(a.code, '') AS key, coalesce(a.legal_name, '(sin aseguradora)') AS label,
             count(*)::int AS lines, count(al.invoice_id)::int AS linked,
             coalesce(sum(al.amount_usd), 0)::float8 AS usd
      FROM avila.authorization_line al
      LEFT JOIN avila.account a ON a.id = al.account_id
      WHERE al.duplicate_of IS NULL
        AND (${months}::int = 0 OR coalesce(al.request_date, al.service_date, al.period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1, 2
      ORDER BY lines DESC
    `,
    db`
      SELECT coalesce(nullif(trim(contratante), ''), '') AS key,
             coalesce(nullif(trim(contratante), ''), '(sin contratante)') AS label,
             count(*)::int AS lines, count(invoice_id)::int AS linked,
             coalesce(sum(amount_usd), 0)::float8 AS usd
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL
        AND (${months}::int = 0 OR coalesce(request_date, service_date, period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1, 2
      ORDER BY lines DESC
      LIMIT 8
    `,
    db`
      SELECT coalesce(pe.code, e.code, '') AS key, coalesce(pe.name_es, e.name_es, '(sin especialidad)') AS label,
             count(*)::int AS lines, count(al.invoice_id)::int AS linked,
             coalesce(sum(al.amount_usd), 0)::float8 AS usd
      FROM avila.authorization_line al
      LEFT JOIN avila.especialidad e ON e.id = al.especialidad_id
      LEFT JOIN avila.especialidad pe ON pe.id = e.parent_id
      WHERE al.duplicate_of IS NULL
        AND (${months}::int = 0 OR coalesce(al.request_date, al.service_date, al.period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1, 2
      ORDER BY lines DESC
      LIMIT 8
    `,
    db`
      SELECT to_char(date_trunc('month', coalesce(request_date, service_date, period_month)), 'YYYY-MM') AS month,
             coalesce(sum(amount_usd), 0)::float8 AS usd,
             count(*)::int AS invoices
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL
        AND coalesce(request_date, service_date, period_month) IS NOT NULL
        AND (${months}::int = 0 OR coalesce(request_date, service_date, period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1
      ORDER BY 1
    `,
    db`
      SELECT CASE
               WHEN d < 0 THEN 'antes'
               WHEN d <= 7 THEN '0-7'
               WHEN d <= 15 THEN '8-15'
               WHEN d <= 30 THEN '16-30'
               WHEN d <= 60 THEN '31-60'
               ELSE '61+'
             END AS key,
             count(*)::int AS n
      FROM (
        SELECT i.issue_date - coalesce(al.request_date, al.service_date) AS d
        FROM avila.authorization_line al
        JOIN avila.invoice i ON i.id = al.invoice_id
        WHERE al.duplicate_of IS NULL
          AND i.issue_date IS NOT NULL
          AND coalesce(al.request_date, al.service_date) IS NOT NULL
          AND (${months}::int = 0 OR coalesce(al.request_date, al.service_date)
               >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      ) x
      GROUP BY 1
    `,
    db`
      SELECT coalesce(match_status, 'sin_evaluar') AS key, count(*)::int AS n
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL AND invoice_id IS NULL
        AND (${months}::int = 0 OR coalesce(request_date, service_date, period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1
      ORDER BY n DESC
    `,
    db`
      SELECT coalesce(date_source, 'sin') AS key, count(*)::int AS n
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL
        AND (${months}::int = 0 OR coalesce(request_date, service_date, period_month)
             >= (date_trunc('month', now()) - make_interval(months => ${months}::int))::date)
      GROUP BY 1
      ORDER BY n DESC
    `,
  ]);
  const f = funnel[0];
  return {
    funnel: {
      lines: f?.lines ?? 0,
      withPerson: f?.with_person ?? 0,
      withDate: f?.with_date ?? 0,
      withExactDate: f?.with_exact_date ?? 0,
      linked: f?.linked ?? 0,
    },
    insurers: insurers as AuthGroupRow[],
    contratantes: contratantes as AuthGroupRow[],
    especialidades: especialidades as AuthGroupRow[],
    trend: fillMonths(trend as AuthTrendPoint[]),
    lag: lag as AuthCountRow[],
    statuses: statuses as AuthCountRow[],
    dateSources: dateSources as AuthCountRow[],
  };
}

export type AuthorizationAnalytics = Awaited<ReturnType<typeof getAuthorizationAnalytics>>;

export type AuthFilterOptions = {
  aseguradoras: { value: string; label: string }[];
  contratantes: { value: string; label: string }[];
  especialidades: { value: string; label: string }[];
  years: string[];
};

export const listAuthorizationFilterOptions = cache(async function listAuthorizationFilterOptions(): Promise<
  AuthFilterOptions
> {
  const db = sql();
  const [aseguradoras, contratantes, especialidades, years] = await Promise.all([
    db`
      SELECT a.code AS value, a.legal_name AS label
      FROM avila.account a
      WHERE EXISTS (SELECT 1 FROM avila.authorization_line al WHERE al.account_id = a.id)
      ORDER BY a.legal_name
    `,
    db`
      SELECT contratante AS value, contratante AS label
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL AND nullif(trim(contratante), '') IS NOT NULL
      GROUP BY contratante
      ORDER BY count(*) DESC, contratante
    `,
    db`
      SELECT coalesce(pe.code, e.code) AS value, coalesce(pe.name_es, e.name_es) AS label
      FROM avila.authorization_line al
      JOIN avila.especialidad e ON e.id = al.especialidad_id
      LEFT JOIN avila.especialidad pe ON pe.id = e.parent_id
      WHERE al.duplicate_of IS NULL
      GROUP BY 1, 2
      ORDER BY 2
    `,
    db`
      SELECT DISTINCT extract(year FROM coalesce(request_date, service_date, period_month))::int::text AS year
      FROM avila.authorization_line
      WHERE duplicate_of IS NULL AND coalesce(request_date, service_date, period_month) IS NOT NULL
      ORDER BY 1 DESC
    `,
  ]);
  return {
    aseguradoras: aseguradoras as AuthFilterOptions["aseguradoras"],
    contratantes: contratantes as AuthFilterOptions["contratantes"],
    especialidades: especialidades as AuthFilterOptions["especialidades"],
    years: years.map((r) => String(r.year)),
  };
});

export type AuthPersonRef = { id: string; full_name: string | null; identity_number: string | null };

export type AuthItemRow = {
  kind: string;
  label: string;
  quantity: string | number | null;
  position: number;
  source_row: string | null;
};

export type AuthSourceRow = { source_file: string; source_row: string | null; created_at: string | Date };

export type AuthCopyRow = { id: string; source_file: string | null; source_row: string | null };

export type AuthReviewRow = {
  id: string;
  kind: string;
  status: string;
  score: number | null;
  invoice_id: string | null;
  invoice_number: string | null;
  resolved_by: string | null;
  resolved_at: string | Date | null;
  created_at: string | Date;
};

export type AuthHistoryRow = {
  id: string;
  entity: string;
  field: string;
  source_kind: string;
  source_ref: string | null;
  rule_id: string;
  reason: string | null;
  confidence: number | null;
  created_at: string | Date;
  script: string | null;
  mode: string | null;
};

export type AuthCandidateRow = {
  id: string;
  invoice_number: string | null;
  issue_date: string | Date | null;
  total_usd: string | number | null;
  account_name: string | null;
  via: "person" | "titular" | "clave" | "review";
  role: string | null;
  gap_days: number | null;
  suggested: boolean;
};

/** Same as Python `match_auth_lines.norm_clave`; empty when there is no usable clave. */
function normClave(value: string | null | undefined): string {
  const digits = (value ?? "").replace(/\D/g, "");
  return digits.length >= 4 ? digits.replace(/^0+/, "") : "";
}

export async function getAuthorizationDetail(id: string) {
  const db = sql();
  const [line] = await db`
    SELECT al.id::text AS id, al.clave_rms, al.aps_code, al.contratante, al.request_date, al.service_date,
           al.period_month, al.date_source, al.diagnosis, al.service_description, al.provider_name,
           al.provider_code, al.provider_rif, al.amount_bs, al.amount_usd, al.coverage_amount,
           al.authorized_amount, al.source_file, al.source_row, al.match_status,
           al.match_score::float8 AS match_score, al.match_signals, al.matched_at,
           al.created_at, al.updated_at, al.duplicate_of::text AS duplicate_of,
           al.person_id::text AS person_id, al.titular_person_id::text AS titular_id,
           al.invoice_id::text AS invoice_id, al.account_id::text AS account_id,
           a.legal_name AS account_name, a.code AS account_code,
           e.name_es AS especialidad, e.code AS especialidad_code, pr.name_es AS procedimiento,
           i.invoice_number, i.issue_date AS invoice_issue_date, i.total_usd AS invoice_total_usd
    FROM avila.authorization_line al
    LEFT JOIN avila.account a ON a.id = al.account_id
    LEFT JOIN avila.especialidad e ON e.id = al.especialidad_id
    LEFT JOIN avila.procedimiento pr ON pr.id = al.procedimiento_id
    LEFT JOIN avila.invoice i ON i.id = al.invoice_id
    WHERE al.id = ${id}::uuid
  `;
  if (!line) return null;
  const clave = normClave(line.clave_rms);

  const [people, items, sources, copies, reviews, history, candidates] = await Promise.all([
    db`
      SELECT p.id::text AS id, p.full_name, p.identity_number
      FROM avila.person p
      WHERE p.id = ANY(ARRAY[nullif(${line.person_id ?? ""}, '')::uuid, nullif(${line.titular_id ?? ""}, '')::uuid])
    `,
    db`
      SELECT kind, label, quantity, position, source_row
      FROM avila.authorization_item
      WHERE authorization_line_id = ${id}::uuid
      ORDER BY position
    `,
    db`
      SELECT source_file, source_row, created_at
      FROM avila.authorization_source
      WHERE authorization_line_id = ${id}::uuid
      ORDER BY created_at, source_file, source_row
    `,
    db`
      SELECT id::text AS id, source_file, source_row
      FROM avila.authorization_line
      WHERE duplicate_of = ${id}::uuid
      ORDER BY created_at
    `,
    db`
      SELECT r.id::text AS id, r.kind, r.status, r.score::float8 AS score,
             r.invoice_id::text AS invoice_id, i.invoice_number,
             r.resolved_by, r.resolved_at, r.created_at
      FROM avila.review_item r
      LEFT JOIN avila.invoice i ON i.id = r.invoice_id
      WHERE r.authorization_line_id = ${id}::uuid
      ORDER BY r.created_at DESC
    `,
    db`
      SELECT fp.id::text AS id, fp.entity, fp.field, fp.source_kind, fp.source_ref, fp.rule_id, fp.reason,
             fp.confidence::float8 AS confidence, fp.created_at, r.script, r.mode
      FROM avila.field_provenance fp
      LEFT JOIN avila.etl_run r ON r.id = fp.run_id
      WHERE (fp.entity = 'authorization_line' AND fp.entity_id = ${id})
         OR (fp.entity = 'authorization_item' AND fp.entity_id IN (
              SELECT ai.id::text FROM avila.authorization_item ai WHERE ai.authorization_line_id = ${id}::uuid))
         OR (fp.entity = 'authorization_source' AND fp.entity_id IN (
              SELECT s.id::text FROM avila.authorization_source s WHERE s.authorization_line_id = ${id}::uuid))
      ORDER BY fp.created_at DESC, fp.id DESC
      LIMIT ${AUTH_HISTORY_LIMIT}
    `,
    db`
      WITH open_review AS (
        SELECT invoice_id FROM avila.review_item
        WHERE authorization_line_id = ${id}::uuid AND kind = 'auth_match' AND status = 'open'
      ),
      pool AS (
        SELECT ip.invoice_id, 'person' AS via, ip.role::text AS role, 0 AS rank
        FROM avila.invoice_person ip WHERE ip.person_id = nullif(${line.person_id ?? ""}, '')::uuid
        UNION ALL
        SELECT ip.invoice_id, 'titular', ip.role::text, 1
        FROM avila.invoice_person ip WHERE ip.person_id = nullif(${line.titular_id ?? ""}, '')::uuid
        UNION ALL
        SELECT i.id, 'clave', NULL, 2
        FROM avila.invoice i
        WHERE ${clave} <> '' AND i.clave IS NOT NULL
          AND ltrim(regexp_replace(i.clave, '[^0-9]', '', 'g'), '0') = ${clave}
        UNION ALL
        SELECT invoice_id, 'review', NULL, 3 FROM open_review
      ),
      best AS (
        SELECT DISTINCT ON (invoice_id) invoice_id, via, role
        FROM pool WHERE invoice_id IS NOT NULL
        ORDER BY invoice_id, rank
      )
      SELECT i.id::text AS id, i.invoice_number, i.issue_date, i.total_usd, a.legal_name AS account_name,
             b.via, b.role,
             (i.issue_date - coalesce(${line.request_date ?? null}::date, ${line.service_date ?? null}::date,
                                      ${line.period_month ?? null}::date))::int AS gap_days,
             EXISTS (SELECT 1 FROM open_review o WHERE o.invoice_id = i.id) AS suggested
      FROM best b
      JOIN avila.invoice i ON i.id = b.invoice_id
      LEFT JOIN avila.account a ON a.id = i.account_id
      WHERE i.id IS DISTINCT FROM nullif(${line.invoice_id ?? ""}, '')::uuid
        AND (nullif(${line.account_id ?? ""}, '')::uuid IS NULL OR i.account_id IS NULL
             OR i.account_id = nullif(${line.account_id ?? ""}, '')::uuid)
      ORDER BY suggested DESC, abs(coalesce((i.issue_date - coalesce(${line.request_date ?? null}::date,
               ${line.service_date ?? null}::date, ${line.period_month ?? null}::date)), 100000)), i.issue_date DESC
      LIMIT ${AUTH_CANDIDATE_LIMIT}
    `,
  ]);

  const byId = new Map((people as AuthPersonRef[]).map((p) => [p.id, p]));
  return {
    line,
    person: line.person_id ? byId.get(line.person_id) ?? null : null,
    titular: line.titular_id ? byId.get(line.titular_id) ?? null : null,
    items: items as AuthItemRow[],
    sources: sources as AuthSourceRow[],
    copies: copies as AuthCopyRow[],
    reviews: reviews as AuthReviewRow[],
    history: history as AuthHistoryRow[],
    candidates: candidates as AuthCandidateRow[],
  };
}

export type AuthorizationDetail = NonNullable<Awaited<ReturnType<typeof getAuthorizationDetail>>>;

export async function getAuthorizationPageTitle(id: string): Promise<string | null> {
  const db = sql();
  const [row] = await db`
    SELECT coalesce(nullif(trim(aps_code), ''), nullif(trim(clave_rms), ''), 'Autorización') AS title
    FROM avila.authorization_line WHERE id = ${id}::uuid
  `;
  return row ? String(row.title) : null;
}

export type AuthLinkResult = "done" | "missing" | "duplicate" | "account_mismatch";

/** Staff link: set the factura, pin the line (`staff`), close open auth_match reviews, add the beneficiario. */
export async function linkAuthorizationToInvoice(
  reviewer: string,
  lineId: string,
  invoiceId: string,
): Promise<AuthLinkResult> {
  const db = sql();
  const [line] = await db`
    SELECT id, invoice_id::text AS invoice_id, person_id::text AS person_id, account_id::text AS account_id,
           duplicate_of
    FROM avila.authorization_line WHERE id = ${lineId}::uuid
  `;
  const [invoice] = await db`
    SELECT id, account_id::text AS account_id FROM avila.invoice WHERE id = ${invoiceId}::uuid
  `;
  if (!line || !invoice) return "missing";
  if (line.duplicate_of) return "duplicate";
  if (line.account_id && invoice.account_id && line.account_id !== invoice.account_id) return "account_mismatch";

  const ref = `/autorizaciones/${lineId}`;
  const reason = `linked by ${reviewer}`;
  const queries = [
    db`
      UPDATE avila.authorization_line
      SET invoice_id = ${invoiceId}::uuid, match_status = 'staff', matched_at = now(), updated_at = now()
      WHERE id = ${lineId}::uuid
    `,
    db`
      INSERT INTO avila.field_provenance (
        entity, entity_id, field, old_value_hash, new_value_hash, source_kind, source_ref, rule_id, reason
      ) VALUES (
        'authorization_line', ${lineId}, 'invoice_id',
        ${line.invoice_id ? valueHash(line.invoice_id) : null}, ${valueHash(invoiceId)},
        'manual', ${ref}, 'staff_link_authorization', ${reason}
      )
    `,
    db`
      UPDATE avila.review_item
      SET status = CASE WHEN invoice_id = ${invoiceId}::uuid THEN 'accepted' ELSE 'rejected' END,
          resolved_by = ${reviewer}, resolved_at = now(), updated_at = now()
      WHERE authorization_line_id = ${lineId}::uuid AND kind = 'auth_match' AND status = 'open'
    `,
  ];
  if (line.person_id) {
    queries.push(
      db`
        INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
        VALUES (${invoiceId}::uuid, ${line.person_id}::uuid, 'beneficiario', 'auth_match')
        ON CONFLICT (invoice_id, person_id) DO UPDATE SET
          role = CASE WHEN avila.invoice_person.role = 'unknown' THEN 'beneficiario' ELSE avila.invoice_person.role END,
          source = CASE
            WHEN avila.invoice_person.source = 'legacy_unknown' THEN 'auth_match'
            ELSE avila.invoice_person.source
          END
      `,
      db`
        INSERT INTO avila.field_provenance (
          entity, entity_id, field, old_value_hash, new_value_hash, source_kind, source_ref, rule_id, reason
        ) VALUES (
          'invoice_person', ${`${invoiceId}:${line.person_id}`}, 'role', NULL, ${valueHash("beneficiario")},
          'manual', ${ref}, 'staff_link_authorization_beneficiario', ${reason}
        )
      `,
    );
  }
  await db.transaction(queries);
  return "done";
}

/** Staff unlink: clear the factura and pin the line so the matcher does not relink it. */
export async function unlinkAuthorization(reviewer: string, lineId: string): Promise<AuthLinkResult> {
  const db = sql();
  const [line] = await db`
    SELECT id, invoice_id::text AS invoice_id, duplicate_of
    FROM avila.authorization_line WHERE id = ${lineId}::uuid
  `;
  if (!line || !line.invoice_id) return "missing";
  if (line.duplicate_of) return "duplicate";

  await db.transaction([
    db`
      UPDATE avila.authorization_line
      SET invoice_id = NULL, match_status = 'staff', matched_at = now(), updated_at = now()
      WHERE id = ${lineId}::uuid
    `,
    db`
      INSERT INTO avila.field_provenance (
        entity, entity_id, field, old_value_hash, new_value_hash, source_kind, source_ref, rule_id, reason
      ) VALUES (
        'authorization_line', ${lineId}, 'invoice_id', ${valueHash(line.invoice_id)}, NULL,
        'manual', ${`/autorizaciones/${lineId}`}, 'staff_unlink_authorization', ${`unlinked by ${reviewer}`}
      )
    `,
    db`
      UPDATE avila.review_item
      SET status = 'rejected', resolved_by = ${reviewer}, resolved_at = now(), updated_at = now()
      WHERE authorization_line_id = ${lineId}::uuid AND kind = 'auth_match' AND status = 'open'
    `,
  ]);
  return "done";
}
