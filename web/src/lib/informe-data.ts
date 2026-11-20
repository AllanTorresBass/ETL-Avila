import { sql } from "./db";
import { getBiData, getEtlData, type BiRange } from "./dashboard-data";

const num = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

async function safe<T>(query: Promise<T>, fallback: T, failures: string[], name: string): Promise<T> {
  try {
    return await query;
  } catch (error) {
    console.error(`[informe] query "${name}" failed`, error);
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

/** Live synthesis of BI fiscal + ETL quality + contact gaps + role/auth cohorts. */
export async function getInformeData(range: BiRange) {
  const db = sql();
  const failures: string[] = [];

  const [bi, etl, contactSummary, contactGaps, roleCohorts] = await Promise.all([
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
          (SELECT count(*)::int FROM avila.invoice) AS invoices
        FROM avila.invoice i
      `,
      [{ with_titular: 0, titular_and_beneficiario: 0, titular_only: 0, invoices: 0 }],
      failures,
      "cohortes de rol",
    ),
  ]);

  failures.push(...bi.failures, ...etl.failures);

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
    },
    authLinkage: {
      lines: authLines,
      linked: authLinked,
      ratio: authLines > 0 ? authLinked / authLines : 0,
    },
  };
}

export type InformeData = Awaited<ReturnType<typeof getInformeData>>;
