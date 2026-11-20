import { IDENTITY_TYPE_LABELS, sql } from "@/lib/db";
import { formatInvoiceNumber, roleLabel } from "@/lib/format";

export const PERSONA_AUTH_PAGE_SIZE = 20;
export const PERSONA_HISTORY_LIMIT = 50;

export const PERSONA_TAB_IDS = [
  "facturas",
  "identidad",
  "autorizaciones",
  "red",
  "archivos",
  "historial",
] as const;

export type PersonaTabId = (typeof PERSONA_TAB_IDS)[number];

export function isPersonaTabId(value: string | undefined | null): value is PersonaTabId {
  return !!value && (PERSONA_TAB_IDS as readonly string[]).includes(value);
}

type LinkedPerson = {
  id: string;
  full_name: string | null;
  identity_number: string | null;
  phone?: string | null;
  invoice_count: number;
  parentesco: string | null;
};

/** Pick the titular with the most shared invoices, then by name. */
export function pickPrimaryTitular(titulares: LinkedPerson[]): LinkedPerson | null {
  if (titulares.length === 0) return null;
  return [...titulares].sort((a, b) => {
    if (b.invoice_count !== a.invoice_count) return b.invoice_count - a.invoice_count;
    const an = (a.full_name || a.identity_number || "").toLowerCase();
    const bn = (b.full_name || b.identity_number || "").toLowerCase();
    return an.localeCompare(bn);
  })[0];
}

export function isIncompleteName(
  fullName: string | null | undefined,
  identityNumber: string | null | undefined,
): boolean {
  const name = (fullName || "").trim();
  if (!name) return true;
  const ci = (identityNumber || "").trim();
  if (ci && name.replace(/\D/g, "") === ci.replace(/\D/g, "") && /\d/.test(name)) return true;
  if (/^\d[\d.\-\s]*$/.test(name)) return true;
  return false;
}

export async function getPersonaDetail(id: string, authPageRaw?: string) {
  const db = sql();

  const [person] = await db`
    SELECT id, identity_type::text AS identity_type, identity_number, full_name,
           birth_date, phone, address, notes, contact_gap
    FROM avila.person WHERE id = ${id}::uuid
  `;
  if (!person) return null;

  const [authCountRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.authorization_line
    WHERE person_id = ${id}::uuid
  `;
  const authTotal = authCountRow?.n ?? 0;
  const authPageMax = Math.max(1, Math.ceil(authTotal / PERSONA_AUTH_PAGE_SIZE));
  const authPage = Math.min(
    authPageMax,
    Math.max(1, Number.parseInt(authPageRaw || "1", 10) || 1),
  );
  const authOffset = (authPage - 1) * PERSONA_AUTH_PAGE_SIZE;

  const invoices = await db`
    SELECT i.id, i.invoice_number, ip.role::text AS role, ip.parentesco,
           a.legal_name AS account
    FROM avila.invoice_person ip
    JOIN avila.invoice i ON i.id = ip.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE ip.person_id = ${id}::uuid
    ORDER BY i.invoice_number
  `;

  const beneficiaries = await db`
    SELECT b.id, b.full_name, b.identity_number,
           count(DISTINCT i.id)::int AS invoice_count,
           max(bip.parentesco) AS parentesco
    FROM avila.invoice_person tip
    JOIN avila.invoice i ON i.id = tip.invoice_id
    JOIN avila.invoice_person bip
      ON bip.invoice_id = tip.invoice_id
     AND bip.role = 'beneficiario'
     AND bip.person_id <> tip.person_id
    JOIN avila.person b ON b.id = bip.person_id
    WHERE tip.person_id = ${id}::uuid
      AND tip.role = 'titular'
    GROUP BY b.id, b.full_name, b.identity_number
    ORDER BY lower(coalesce(b.full_name, '')), b.identity_number
  `;

  const titulares = await db`
    SELECT t.id, t.full_name, t.identity_number, t.phone,
           count(DISTINCT i.id)::int AS invoice_count,
           max(bip.parentesco) AS parentesco
    FROM avila.invoice_person bip
    JOIN avila.invoice i ON i.id = bip.invoice_id
    JOIN avila.invoice_person tip
      ON tip.invoice_id = bip.invoice_id
     AND tip.role = 'titular'
     AND tip.person_id <> bip.person_id
    JOIN avila.person t ON t.id = tip.person_id
    WHERE bip.person_id = ${id}::uuid
      AND bip.role = 'beneficiario'
    GROUP BY t.id, t.full_name, t.identity_number, t.phone
    ORDER BY lower(coalesce(t.full_name, '')), t.identity_number
  `;

  const sourceFilesPrimary = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.backup_path,
           sf.invoice_id, i.invoice_number, sf.rule_id
    FROM avila.source_file sf
    JOIN avila.invoice i ON i.id = sf.invoice_id
    WHERE sf.invoice_id IN (
      SELECT invoice_id FROM avila.invoice_person WHERE person_id = ${id}::uuid
    )
    ORDER BY sf.id, i.invoice_number, sf.file_label
  `;

  const sourceFilesFallback = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.backup_path,
           sf.invoice_id, i.invoice_number, sf.rule_id
    FROM avila.document d
    JOIN avila.source_file sf ON sf.id = d.source_file_id
    LEFT JOIN avila.invoice i ON i.id = sf.invoice_id
    WHERE d.person_id = ${id}::uuid
      AND (
        sf.invoice_id IS NULL
        OR NOT EXISTS (
          SELECT 1 FROM avila.invoice_person ip
          WHERE ip.person_id = ${id}::uuid AND ip.invoice_id = sf.invoice_id
        )
      )
    ORDER BY sf.id, sf.file_label
  `;

  const sourceFileMap = new Map<string, (typeof sourceFilesPrimary)[number]>();
  for (const f of [...sourceFilesPrimary, ...sourceFilesFallback]) {
    sourceFileMap.set(f.id, f);
  }
  const sourceFiles = [...sourceFileMap.values()].sort((a, b) => {
    const an = a.invoice_number || "";
    const bn = b.invoice_number || "";
    if (an !== bn) return an.localeCompare(bn);
    const ap = a.backup_path || a.file_label || "";
    const bp = b.backup_path || b.file_label || "";
    return ap.localeCompare(bp);
  });

  const lines = await db`
    SELECT id, clave_rms, contratante, service_date, request_date, diagnosis,
           service_description, provider_name, amount_bs, amount_usd,
           coverage_amount, authorized_amount, invoice_id
    FROM avila.authorization_line
    WHERE person_id = ${id}::uuid
    ORDER BY coalesce(service_date, request_date) DESC NULLS LAST, created_at DESC
    LIMIT ${PERSONA_AUTH_PAGE_SIZE} OFFSET ${authOffset}
  `;

  const identityDocs = await db`
    SELECT id, page_index, document_type::text AS document_type,
           upload_status::text AS upload_status
    FROM avila.document
    WHERE person_id = ${id}::uuid
    ORDER BY page_index, document_type
  `;

  const expedienteDocs = await db`
    SELECT d.id, d.page_index, d.document_type::text AS document_type,
           d.upload_status::text AS upload_status, d.invoice_id, i.invoice_number
    FROM avila.document d
    JOIN avila.invoice i ON i.id = d.invoice_id
    WHERE d.invoice_id IN (
      SELECT invoice_id FROM avila.invoice_person WHERE person_id = ${id}::uuid
    )
    AND (d.person_id IS DISTINCT FROM ${id}::uuid)
    ORDER BY i.invoice_number, d.page_index, d.document_type
  `;

  const invoicePersonKeys = invoices.map((i) => `${i.id}:${id}`);
  const history = await db`
    SELECT fp.id, fp.entity, fp.field, fp.source_kind, fp.source_ref, fp.rule_id,
           fp.confidence, fp.reason, fp.created_at, r.script
    FROM avila.field_provenance fp
    LEFT JOIN avila.etl_run r ON r.id = fp.run_id
    WHERE (fp.entity = 'person' AND fp.entity_id = ${id})
       OR (fp.entity = 'invoice_person' AND fp.entity_id = ANY(${invoicePersonKeys}))
    ORDER BY fp.created_at DESC, fp.id DESC
    LIMIT ${PERSONA_HISTORY_LIMIT}
  `;

  const invoiceIds = invoices.map((i) => i.id as string);
  const openReviewsRow = invoiceIds.length
    ? await db`
        SELECT count(*)::int AS n
        FROM avila.review_item
        WHERE status = 'open'
          AND (
            person_id = ${id}::uuid
            OR other_person_id = ${id}::uuid
            OR invoice_id = ANY(${invoiceIds})
          )
      `
    : await db`
        SELECT count(*)::int AS n
        FROM avila.review_item
        WHERE status = 'open'
          AND (person_id = ${id}::uuid OR other_person_id = ${id}::uuid)
      `;
  const openReviews = openReviewsRow[0]?.n ?? 0;

  const identityType =
    IDENTITY_TYPE_LABELS[person.identity_type] || person.identity_type;
  const identityLine = `${identityType}: ${person.identity_number || "—"}`;

  const roleCounts = new Map<string, number>();
  for (const inv of invoices) {
    if (inv.role !== "titular" && inv.role !== "beneficiario") continue;
    roleCounts.set(inv.role, (roleCounts.get(inv.role) || 0) + 1);
  }

  const expedienteByInvoice = new Map<
    string,
    { invoiceId: string; invoiceNumber: string; docs: typeof expedienteDocs }
  >();
  for (const doc of expedienteDocs) {
    const key = doc.invoice_id || "none";
    const existing = expedienteByInvoice.get(key);
    if (existing) {
      existing.docs.push(doc);
    } else {
      expedienteByInvoice.set(key, {
        invoiceId: doc.invoice_id,
        invoiceNumber: doc.invoice_number,
        docs: [doc],
      });
    }
  }

  const facturaBlocks = new Map<
    string,
    {
      id: string;
      title: string;
      href: string;
      roles: string[];
      parentesco: string | null;
      account: string | null;
    }
  >();
  for (const inv of invoices) {
    const role = roleLabel(inv.role);
    const parentesco = inv.parentesco ? String(inv.parentesco) : null;
    const existing = facturaBlocks.get(inv.id);
    if (existing) {
      if (!existing.roles.includes(role)) existing.roles.push(role);
      if (!existing.parentesco && parentesco) existing.parentesco = parentesco;
    } else {
      facturaBlocks.set(inv.id, {
        id: inv.id,
        title: formatInvoiceNumber(inv.invoice_number),
        href: `/facturas/${inv.id}`,
        roles: [role],
        parentesco,
        account: inv.account ? String(inv.account) : null,
      });
    }
  }

  const primaryTitular = pickPrimaryTitular(titulares as LinkedPerson[]);

  return {
    person,
    identityType,
    identityLine,
    incompleteName: isIncompleteName(person.full_name, person.identity_number),
    roleCounts,
    invoices,
    beneficiaries,
    titulares,
    primaryTitular,
    sourceFiles,
    authTotal,
    authPage,
    authOffset,
    lines,
    identityDocs,
    expedienteDocs,
    expedienteByInvoice,
    facturaBlocks,
    history,
    openReviews,
  };
}

export type PersonaDetail = NonNullable<Awaited<ReturnType<typeof getPersonaDetail>>>;

/** Resolve which dossier tab to show first. */
export function resolvePersonaDefaultTab(
  tabParam: string | undefined,
  detail: Pick<
    PersonaDetail,
    | "invoices"
    | "identityDocs"
    | "authTotal"
    | "titulares"
    | "beneficiaries"
    | "sourceFiles"
    | "history"
  >,
): PersonaTabId {
  if (isPersonaTabId(tabParam)) return tabParam;

  if (detail.invoices.length > 0) return "facturas";
  if (detail.identityDocs.length > 0) return "identidad";
  if (detail.authTotal > 0) return "autorizaciones";
  if (detail.titulares.length > 0 || detail.beneficiaries.length > 0) return "red";
  if (detail.sourceFiles.length > 0) return "archivos";
  return "historial";
}
