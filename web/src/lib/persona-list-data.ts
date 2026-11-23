import { sql } from "@/lib/db";

export type PersonaListRow = {
  id: string;
  identity_type: string;
  identity_number: string | null;
  full_name: string | null;
  phone: string | null;
  birth_date: string | Date | null;
  contact_gap: unknown;
  docs: number;
  titular_n: number;
  beneficiario_n: number;
};

export type PersonaListFilters = {
  query: string;
  like: string;
  hasCi: string;
  hasPhone: string;
  hasAuthorization: string;
  hasInvoice: string;
  hasContactGap: string;
  incompleteName: string;
  roleFilter: string;
  account: string;
  pageSize: number;
  requestedPage: number;
  exportLimit: number;
};

export async function queryPersonaList(filters: PersonaListFilters): Promise<{
  total: number;
  page: number;
  pageRows: PersonaListRow[];
  exportRows: PersonaListRow[];
}> {
  const {
    query,
    like,
    hasCi,
    hasPhone,
    hasAuthorization,
    hasInvoice,
    hasContactGap,
    incompleteName,
    roleFilter,
    account,
    pageSize,
    requestedPage,
    exportLimit,
  } = filters;
  const db = sql();

  const [countRow] = await db`
    SELECT count(DISTINCT p.id)::int AS n
    FROM avila.person p
    LEFT JOIN avila.authorization_line al ON al.person_id = p.id
    LEFT JOIN avila.invoice_person ip ON ip.person_id = p.id
    LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE (${query} = '' OR p.identity_number ILIKE ${like}
           OR coalesce(p.full_name, '') ILIKE ${like}
           OR coalesce(p.phone, '') ILIKE ${like}
           OR coalesce(al.clave_rms, '') ILIKE ${like})
      AND (${hasCi} = '' OR (${hasCi} = '1' AND p.identity_number IS NOT NULL AND p.identity_number <> '')
           OR (${hasCi} = '0' AND (p.identity_number IS NULL OR p.identity_number = '')))
      AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p.phone IS NOT NULL AND p.phone <> '')
           OR (${hasPhone} = '0' AND (p.phone IS NULL OR p.phone = '')))
      AND (${hasAuthorization} = '' OR (${hasAuthorization} = '1' AND EXISTS (
             SELECT 1 FROM avila.authorization_line alx
             WHERE alx.person_id = p.id AND alx.duplicate_of IS NULL
           ))
           OR (${hasAuthorization} = '0' AND NOT EXISTS (
             SELECT 1 FROM avila.authorization_line alx
             WHERE alx.person_id = p.id AND alx.duplicate_of IS NULL
           )))
      AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
             SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p.id
           ))
           OR (${hasInvoice} = '0' AND NOT EXISTS (
             SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p.id
           )))
      AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p.contact_gap IS NOT NULL
           AND (
             coalesce(p.contact_gap->>'birth_date', 'filled') <> 'filled'
             OR coalesce(p.contact_gap->>'phone', 'filled') <> 'filled'
             OR coalesce(p.contact_gap->>'address', 'filled') <> 'filled'
           )))
      AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
             coalesce(nullif(trim(p.full_name), ''), '') = ''
             OR (
               p.identity_number IS NOT NULL
               AND regexp_replace(coalesce(p.full_name, ''), '\\D', '', 'g')
                 = regexp_replace(p.identity_number, '\\D', '', 'g')
               AND p.full_name ~ '[0-9]'
             )
             OR coalesce(p.full_name, '') ~* 'venezolan|nacionalidad|cedula[[:space:]]+de[[:space:]]+identidad|\\yapellido|\\ynombre'
             OR coalesce(p.full_name, '') ~ '^20[2-3][0-9]{5}'
             OR coalesce(p.identity_number, '') ~ '^20[2-3][0-9]{5}$'
             OR (
               coalesce(p.full_name, '') <> ''
               AND array_length(regexp_split_to_array(trim(p.full_name), '[[:space:]]+'), 1) < 2
             )
           )))
      AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
      AND (${account} = '' OR a.code = ${account})
  `;

  const total = countRow?.n ?? 0;
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  const offset = (page - 1) * pageSize;

  const [pageRows, exportRows] = await Promise.all([
    db`
      SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
             p.phone, p.birth_date, p.contact_gap,
             coalesce(dc.docs, 0)::int AS docs,
             coalesce(roles.titular_n, 0)::int AS titular_n,
             coalesce(roles.beneficiario_n, 0)::int AS beneficiario_n
      FROM avila.person p
      LEFT JOIN (
        SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
      ) dc ON dc.person_id = p.id
      LEFT JOIN (
        SELECT person_id,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'titular')::int AS titular_n,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'beneficiario')::int AS beneficiario_n
        FROM avila.invoice_person
        GROUP BY person_id
      ) roles ON roles.person_id = p.id
      WHERE p.id IN (
        SELECT DISTINCT p2.id
        FROM avila.person p2
        LEFT JOIN avila.authorization_line al ON al.person_id = p2.id
        LEFT JOIN avila.invoice_person ip ON ip.person_id = p2.id
        LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE (${query} = '' OR p2.identity_number ILIKE ${like}
               OR coalesce(p2.full_name, '') ILIKE ${like}
               OR coalesce(p2.phone, '') ILIKE ${like}
               OR coalesce(al.clave_rms, '') ILIKE ${like})
          AND (${hasCi} = '' OR (${hasCi} = '1' AND p2.identity_number IS NOT NULL AND p2.identity_number <> '')
               OR (${hasCi} = '0' AND (p2.identity_number IS NULL OR p2.identity_number = '')))
          AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p2.phone IS NOT NULL AND p2.phone <> '')
               OR (${hasPhone} = '0' AND (p2.phone IS NULL OR p2.phone = '')))
          AND (${hasAuthorization} = '' OR (${hasAuthorization} = '1' AND EXISTS (
                 SELECT 1 FROM avila.authorization_line alx
                 WHERE alx.person_id = p2.id AND alx.duplicate_of IS NULL
               ))
               OR (${hasAuthorization} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.authorization_line alx
                 WHERE alx.person_id = p2.id AND alx.duplicate_of IS NULL
               )))
          AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               ))
               OR (${hasInvoice} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               )))
          AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p2.contact_gap IS NOT NULL
               AND (
                 coalesce(p2.contact_gap->>'birth_date', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'phone', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'address', 'filled') <> 'filled'
               )))
          AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
                 coalesce(nullif(trim(p2.full_name), ''), '') = ''
                 OR (
                   p2.identity_number IS NOT NULL
                   AND regexp_replace(coalesce(p2.full_name, ''), '\\D', '', 'g')
                     = regexp_replace(p2.identity_number, '\\D', '', 'g')
                   AND p2.full_name ~ '[0-9]'
                 )
                 OR coalesce(p2.full_name, '') ~* 'venezolan|nacionalidad|cedula[[:space:]]+de[[:space:]]+identidad|\\yapellido|\\ynombre'
                 OR coalesce(p2.full_name, '') ~ '^20[2-3][0-9]{5}'
                 OR coalesce(p2.identity_number, '') ~ '^20[2-3][0-9]{5}$'
                 OR (
                   coalesce(p2.full_name, '') <> ''
                   AND array_length(regexp_split_to_array(trim(p2.full_name), '[[:space:]]+'), 1) < 2
                 )
               )))
          AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
          AND (${account} = '' OR a.code = ${account})
      )
      ORDER BY lower(nullif(trim(p.full_name), '')) ASC NULLS LAST,
               p.identity_number NULLS LAST,
               p.created_at DESC
      LIMIT ${pageSize} OFFSET ${offset}
    `,
    db`
      SELECT p.id, p.identity_type::text AS identity_type, p.identity_number, p.full_name,
             p.phone, p.birth_date, p.contact_gap,
             coalesce(dc.docs, 0)::int AS docs,
             coalesce(roles.titular_n, 0)::int AS titular_n,
             coalesce(roles.beneficiario_n, 0)::int AS beneficiario_n
      FROM avila.person p
      LEFT JOIN (
        SELECT person_id, count(*)::int AS docs FROM avila.document GROUP BY person_id
      ) dc ON dc.person_id = p.id
      LEFT JOIN (
        SELECT person_id,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'titular')::int AS titular_n,
               count(DISTINCT invoice_id) FILTER (WHERE role = 'beneficiario')::int AS beneficiario_n
        FROM avila.invoice_person
        GROUP BY person_id
      ) roles ON roles.person_id = p.id
      WHERE p.id IN (
        SELECT DISTINCT p2.id
        FROM avila.person p2
        LEFT JOIN avila.authorization_line al ON al.person_id = p2.id
        LEFT JOIN avila.invoice_person ip ON ip.person_id = p2.id
        LEFT JOIN avila.invoice i ON i.id = ip.invoice_id
        LEFT JOIN avila.account a ON a.id = i.account_id
        WHERE (${query} = '' OR p2.identity_number ILIKE ${like}
               OR coalesce(p2.full_name, '') ILIKE ${like}
               OR coalesce(p2.phone, '') ILIKE ${like}
               OR coalesce(al.clave_rms, '') ILIKE ${like})
          AND (${hasCi} = '' OR (${hasCi} = '1' AND p2.identity_number IS NOT NULL AND p2.identity_number <> '')
               OR (${hasCi} = '0' AND (p2.identity_number IS NULL OR p2.identity_number = '')))
          AND (${hasPhone} = '' OR (${hasPhone} = '1' AND p2.phone IS NOT NULL AND p2.phone <> '')
               OR (${hasPhone} = '0' AND (p2.phone IS NULL OR p2.phone = '')))
          AND (${hasAuthorization} = '' OR (${hasAuthorization} = '1' AND EXISTS (
                 SELECT 1 FROM avila.authorization_line alx
                 WHERE alx.person_id = p2.id AND alx.duplicate_of IS NULL
               ))
               OR (${hasAuthorization} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.authorization_line alx
                 WHERE alx.person_id = p2.id AND alx.duplicate_of IS NULL
               )))
          AND (${hasInvoice} = '' OR (${hasInvoice} = '1' AND EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               ))
               OR (${hasInvoice} = '0' AND NOT EXISTS (
                 SELECT 1 FROM avila.invoice_person ipx WHERE ipx.person_id = p2.id
               )))
          AND (${hasContactGap} = '' OR (${hasContactGap} = '1' AND p2.contact_gap IS NOT NULL
               AND (
                 coalesce(p2.contact_gap->>'birth_date', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'phone', 'filled') <> 'filled'
                 OR coalesce(p2.contact_gap->>'address', 'filled') <> 'filled'
               )))
          AND (${incompleteName} = '' OR (${incompleteName} = '1' AND (
                 coalesce(nullif(trim(p2.full_name), ''), '') = ''
                 OR (
                   p2.identity_number IS NOT NULL
                   AND regexp_replace(coalesce(p2.full_name, ''), '\\D', '', 'g')
                     = regexp_replace(p2.identity_number, '\\D', '', 'g')
                   AND p2.full_name ~ '[0-9]'
                 )
                 OR coalesce(p2.full_name, '') ~* 'venezolan|nacionalidad|cedula[[:space:]]+de[[:space:]]+identidad|\\yapellido|\\ynombre'
                 OR coalesce(p2.full_name, '') ~ '^20[2-3][0-9]{5}'
                 OR coalesce(p2.identity_number, '') ~ '^20[2-3][0-9]{5}$'
                 OR (
                   coalesce(p2.full_name, '') <> ''
                   AND array_length(regexp_split_to_array(trim(p2.full_name), '[[:space:]]+'), 1) < 2
                 )
               )))
          AND (${roleFilter} = '' OR ip.role::text = ${roleFilter})
          AND (${account} = '' OR a.code = ${account})
      )
      ORDER BY lower(nullif(trim(p.full_name), '')) ASC NULLS LAST,
               p.identity_number NULLS LAST,
               p.created_at DESC
      LIMIT ${exportLimit}
    `,
  ]);

  return {
    total,
    page,
    pageRows: pageRows as PersonaListRow[],
    exportRows: exportRows as PersonaListRow[],
  };
}
