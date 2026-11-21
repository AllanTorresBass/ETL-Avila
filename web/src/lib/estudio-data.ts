import { sql } from "@/lib/db";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { clampPage } from "@/components/pagination";

export const ESTUDIO_FAMILIES: { id: string; label: string; codes: string[] }[] = [
  { id: "laboratorio", label: "Laboratorio", codes: ["examenes_laboratorio", "serologia", "antibiograma"] },
  {
    id: "corazon",
    label: "Corazón",
    codes: ["ecocardiograma", "electrocardiograma", "holter", "prueba_esfuerzo", "coronariografia", "mapa"],
  },
  { id: "ecografia", label: "Ecografía", codes: ["ecografia", "ecomamografia"] },
  { id: "rayos_x", label: "Rayos X", codes: ["rayos_x", "fistulografia"] },
  { id: "tomografia", label: "Tomografía", codes: ["tomografia", "angiotomografia"] },
  { id: "resonancia", label: "Resonancia", codes: ["resonancia"] },
  {
    id: "endoscopia",
    label: "Endoscopia",
    codes: ["endoscopia_digestiva", "colonoscopia", "colposcopia", "cistoscopia", "laringoscopia"],
  },
  { id: "mamografia", label: "Mamografía", codes: ["mamografia"] },
  { id: "densitometria", label: "Densitometría", codes: ["densitometria"] },
  { id: "anatomia_patologica", label: "Biopsia / citología", codes: ["citologia", "biopsia"] },
  {
    id: "funcional",
    label: "Pruebas funcionales",
    codes: ["audiometria", "electromiografia", "electroencefalograma", "espirometria", "flujometria"],
  },
  { id: "medicina_nuclear", label: "Medicina nuclear", codes: ["gammagrama"] },
  { id: "oftalmologia", label: "Oftalmología", codes: ["fluororetinografia", "campo_visual"] },
  { id: "sin_nombre", label: "Orden sin nombre", codes: [] },
];

const FAMILY_BY_CODE = new Map(ESTUDIO_FAMILIES.flatMap((family) => family.codes.map((code) => [code, family.label])));

export function familyLabel(code: string | null): string {
  if (!code) return "Orden sin nombre";
  return FAMILY_BY_CODE.get(code) || code;
}

export function isEstudioFamily(value: string): boolean {
  return ESTUDIO_FAMILIES.some((family) => family.id === value);
}

export const ESTUDIO_SOURCE_LABELS: Record<string, string> = {
  fiscal_line: "Cargo de la factura",
  result_page: "Hoja de resultado",
  study_order: "Orden de estudio",
};

export const ESTUDIO_STATUS_LABELS: Record<string, string> = {
  matched: "Con estudio",
  unmatched: "Sin nombre",
  review: "Paciente por confirmar",
};

export type EstudioSummary = {
  facturas: number;
  charged: number;
  withResult: number;
  chargedWithoutResult: number;
  families: { id: string; label: string; n: number }[];
};

export const EMPTY_ESTUDIO_SUMMARY: EstudioSummary = {
  facturas: 0,
  charged: 0,
  withResult: 0,
  chargedWithoutResult: 0,
  families: [],
};

export type EstudioLine = {
  id: string;
  source: string;
  serviceLabel: string;
  procedimientoCode: string | null;
  procedimientoName: string | null;
  familyLabel: string;
  linkStatus: string;
  invoiceId: string;
  invoiceNumber: string | null;
  issueDate: string | null;
};

export type EstudioInvoiceRow = {
  id: string;
  invoiceNumber: string | null;
  issueDate: string | null;
  patientName: string | null;
  labels: string[];
  charged: boolean;
  hasResult: boolean;
};

const num = (value: unknown) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

const text = (value: unknown) => (value == null || value === "" ? null : String(value));

const labelsOf = (value: unknown): string[] => (Array.isArray(value) ? value.map((item) => String(item)) : []);

function familyCodes(familyId: string): string[] {
  return ESTUDIO_FAMILIES.find((family) => family.id === familyId)?.codes ?? [];
}

export async function getEstudioSummary(): Promise<EstudioSummary> {
  const db = sql();
  const namedFamilies = ESTUDIO_FAMILIES.filter((family) => family.codes.length > 0);
  const [totals, unnamed, ...familyCounts] = await Promise.all([
    db`
      SELECT
        count(DISTINCT invoice_id) FILTER (WHERE kind = 'estudio')::int AS facturas,
        count(DISTINCT invoice_id) FILTER (WHERE kind = 'estudio' AND source = 'fiscal_line')::int AS charged,
        count(DISTINCT invoice_id) FILTER (WHERE kind = 'estudio' AND source = 'result_page')::int AS with_result,
        count(DISTINCT invoice_id) FILTER (
          WHERE kind = 'estudio' AND source = 'fiscal_line'
            AND NOT EXISTS (
              SELECT 1 FROM avila.invoice_service r
              WHERE r.invoice_id = avila.invoice_service.invoice_id
                AND r.kind = 'estudio'
                AND r.source = 'result_page'
            )
        )::int AS charged_without_result
      FROM avila.invoice_service
    `,
    db`
      SELECT count(DISTINCT invoice_id)::int AS n
      FROM avila.invoice_service
      WHERE kind = 'estudio' AND source = 'study_order' AND procedimiento_id IS NULL
    `,
    ...namedFamilies.map((family) =>
      db`
        SELECT count(DISTINCT s.invoice_id)::int AS n
        FROM avila.invoice_service s
        JOIN avila.procedimiento pr ON pr.id = s.procedimiento_id
        WHERE s.kind = 'estudio' AND pr.code = ANY(${family.codes})
      `,
    ),
  ]);
  const counts = new Map<string, number>();
  namedFamilies.forEach((family, index) => {
    counts.set(family.id, num(familyCounts[index]?.[0]?.n));
  });
  if (num(unnamed[0]?.n) > 0) counts.set("sin_nombre", num(unnamed[0]?.n));
  const header = totals[0];
  return {
    facturas: num(header?.facturas),
    charged: num(header?.charged),
    withResult: num(header?.with_result),
    chargedWithoutResult: num(header?.charged_without_result),
    families: ESTUDIO_FAMILIES.map((family) => ({
      id: family.id,
      label: family.label,
      n: counts.get(family.id) || 0,
    })).filter((family) => family.n > 0),
  };
}

function mapLine(row: Record<string, unknown>): EstudioLine {
  const code = text(row.procedimiento_code);
  return {
    id: String(row.id),
    source: String(row.source),
    serviceLabel: String(row.service_label || ""),
    procedimientoCode: code,
    procedimientoName: text(row.procedimiento_name),
    familyLabel: familyLabel(code),
    linkStatus: String(row.link_status || ""),
    invoiceId: String(row.invoice_id),
    invoiceNumber: text(row.invoice_number),
    issueDate: text(row.issue_date)?.slice(0, 10) ?? null,
  };
}

export async function queryEstudiosForInvoice(invoiceId: string): Promise<EstudioLine[]> {
  const db = sql();
  const rows = await db`
    SELECT s.id::text AS id,
           s.source,
           s.service_label,
           s.link_status,
           pr.code AS procedimiento_code,
           pr.name_es AS procedimiento_name,
           i.id::text AS invoice_id,
           i.invoice_number,
           i.issue_date::text AS issue_date
    FROM avila.invoice_service s
    JOIN avila.invoice i ON i.id = s.invoice_id
    LEFT JOIN avila.procedimiento pr ON pr.id = s.procedimiento_id
    WHERE s.kind = 'estudio' AND s.invoice_id = ${invoiceId}::uuid
    ORDER BY s.source, s.line_no
  `;
  return rows.map((row) => mapLine(row));
}

export async function queryEstudiosForPerson(personId: string): Promise<EstudioLine[]> {
  const db = sql();
  const rows = await db`
    SELECT s.id::text AS id,
           s.source,
           s.service_label,
           s.link_status,
           pr.code AS procedimiento_code,
           pr.name_es AS procedimiento_name,
           i.id::text AS invoice_id,
           i.invoice_number,
           i.issue_date::text AS issue_date
    FROM avila.invoice_service s
    JOIN avila.invoice i ON i.id = s.invoice_id
    LEFT JOIN avila.procedimiento pr ON pr.id = s.procedimiento_id
    WHERE s.kind = 'estudio'
      AND s.invoice_id IN (
        SELECT ip.invoice_id FROM avila.invoice_person ip WHERE ip.person_id = ${personId}::uuid
      )
    ORDER BY i.issue_date DESC NULLS LAST, i.invoice_number, s.source, s.line_no
  `;
  return rows.map((row) => mapLine(row));
}

export async function queryEstudioList(input: { query: string; family: string; page: number }) {
  const db = sql();
  const family = isEstudioFamily(input.family) ? input.family : "";
  const codes = familyCodes(family);
  const like = input.query ? `%${input.query}%` : "";
  const pageSize = LIST_PAGE_SIZE;
  const [countRow] = await db`
    SELECT count(*)::int AS n
    FROM (
      SELECT i.id
      FROM avila.invoice i
      JOIN avila.invoice_service s ON s.invoice_id = i.id
      LEFT JOIN avila.procedimiento pr ON pr.id = s.procedimiento_id
      LEFT JOIN LATERAL (
        SELECT pe.full_name
        FROM avila.invoice_person ip
        JOIN avila.person pe ON pe.id = ip.person_id
        WHERE ip.invoice_id = i.id AND ip.role IN ('beneficiario', 'titular')
        ORDER BY CASE ip.role WHEN 'beneficiario' THEN 0 ELSE 1 END
        LIMIT 1
      ) patient ON true
      WHERE s.kind = 'estudio'
        AND (
          ${family} = ''
          OR (${family} = 'sin_nombre' AND s.procedimiento_id IS NULL AND s.source = 'study_order')
          OR pr.code = ANY(${codes})
        )
        AND (
          ${input.query} = ''
          OR i.invoice_number ILIKE ${like}
          OR patient.full_name ILIKE ${like}
        )
      GROUP BY i.id
    ) matched
  `;
  const total = num(countRow?.n);
  const page = clampPage(input.page, total, pageSize);
  const offset = (page - 1) * pageSize;
  const rows = await db`
    SELECT i.id::text AS id,
           i.invoice_number,
           i.issue_date::text AS issue_date,
           patient.full_name AS patient_name,
           array_agg(DISTINCT s.service_label) AS labels,
           bool_or(s.source = 'fiscal_line') AS charged,
           bool_or(s.source = 'result_page') AS has_result
    FROM avila.invoice i
    JOIN avila.invoice_service s ON s.invoice_id = i.id
    LEFT JOIN avila.procedimiento pr ON pr.id = s.procedimiento_id
    LEFT JOIN LATERAL (
      SELECT pe.full_name
      FROM avila.invoice_person ip
      JOIN avila.person pe ON pe.id = ip.person_id
      WHERE ip.invoice_id = i.id AND ip.role IN ('beneficiario', 'titular')
      ORDER BY CASE ip.role WHEN 'beneficiario' THEN 0 ELSE 1 END
      LIMIT 1
    ) patient ON true
    WHERE s.kind = 'estudio'
      AND (
        ${family} = ''
        OR (${family} = 'sin_nombre' AND s.procedimiento_id IS NULL AND s.source = 'study_order')
        OR pr.code = ANY(${codes})
      )
      AND (
        ${input.query} = ''
        OR i.invoice_number ILIKE ${like}
        OR patient.full_name ILIKE ${like}
      )
    GROUP BY i.id, i.invoice_number, i.issue_date, patient.full_name
    ORDER BY i.issue_date DESC NULLS LAST, i.invoice_number
    LIMIT ${pageSize} OFFSET ${offset}
  `;
  return {
    total,
    page,
    rows: rows.map(
      (row): EstudioInvoiceRow => ({
        id: String(row.id),
        invoiceNumber: text(row.invoice_number),
        issueDate: text(row.issue_date)?.slice(0, 10) ?? null,
        patientName: text(row.patient_name),
        labels: labelsOf(row.labels).slice(0, 6),
        charged: Boolean(row.charged),
        hasResult: Boolean(row.has_result),
      }),
    ),
  };
}

export function estudioListPage(raw: string | null): number {
  return requestedPage(raw);
}
