import { sql } from "@/lib/db";

export type AccountOption = { code: string; legal_name: string };

export async function listAccounts(): Promise<AccountOption[]> {
  const db = sql();
  const rows = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;
  return rows as AccountOption[];
}

export async function listInvoiceYears(): Promise<{ y: string }[]> {
  const db = sql();
  const rows = await db`
    SELECT DISTINCT year AS y FROM avila.invoice
    WHERE year IS NOT NULL AND year <> ''
    ORDER BY year DESC
  `;
  return rows as { y: string }[];
}

export async function listInvoiceMonths(): Promise<{ m: string }[]> {
  const db = sql();
  const rows = await db`
    SELECT DISTINCT month AS m FROM avila.invoice
    WHERE month IS NOT NULL AND month <> ''
    ORDER BY month
  `;
  return rows as { m: string }[];
}
