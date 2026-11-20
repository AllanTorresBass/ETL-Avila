import { cache } from "react";
import { sql } from "@/lib/db";

/** Corpus-level KPIs for the Facturas list (filter shortcuts, not result-scoped). */
export const getFacturaListKpis = cache(async function getFacturaListKpis() {
  const db = sql();
  const [row] = await db`
    SELECT
      count(*)::int AS total,
      count(*) FILTER (
        WHERE EXISTS (
          SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
        )
      )::int AS with_person,
      count(*) FILTER (
        WHERE NOT EXISTS (
          SELECT 1 FROM avila.invoice_person ip WHERE ip.invoice_id = i.id
        )
      )::int AS without_person,
      count(*) FILTER (
        WHERE EXISTS (
          SELECT 1 FROM avila.invoice_person tip
          WHERE tip.invoice_id = i.id AND tip.role = 'titular'
        )
      )::int AS with_titular,
      count(*) FILTER (
        WHERE NOT EXISTS (
          SELECT 1 FROM avila.invoice_person tip
          WHERE tip.invoice_id = i.id AND tip.role = 'titular'
        )
      )::int AS without_titular,
      count(*) FILTER (
        WHERE EXISTS (
          SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
        )
      )::int AS with_docs,
      count(*) FILTER (
        WHERE NOT EXISTS (
          SELECT 1 FROM avila.document d WHERE d.invoice_id = i.id
        )
      )::int AS without_docs
    FROM avila.invoice i
  `;

  const [reviews] = await db`
    SELECT count(*)::int AS n
    FROM avila.review_item
    WHERE status = 'open'
      AND invoice_id IS NOT NULL
  `;

  return {
    total: row?.total ?? 0,
    withPerson: row?.with_person ?? 0,
    withoutPerson: row?.without_person ?? 0,
    withTitular: row?.with_titular ?? 0,
    withoutTitular: row?.without_titular ?? 0,
    withDocs: row?.with_docs ?? 0,
    withoutDocs: row?.without_docs ?? 0,
    openInvoiceReviews: reviews?.n ?? 0,
  };
});

export type FacturaListKpis = Awaited<ReturnType<typeof getFacturaListKpis>>;
