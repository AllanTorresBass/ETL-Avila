import { cache } from "react";
import { sql } from "@/lib/db";

export const MEDICO_ATENCION_LIMIT = 50;
export const MEDICO_PATIENT_LIMIT = 50;
export const ESPECIALIDAD_BACKLOG_LIMIT = 50;

export const REPORT_KIND_LABELS: Record<string, string> = {
  informe: "Informe médico",
  orden: "Orden",
  laboratorio: "Laboratorio",
  imagen: "Imagenología",
};

export const LINK_STATUS_LABELS: Record<string, string> = {
  complete: "Completa",
  partial: "Parcial",
  review: "En revisión",
  unmatched: "Sin vínculo",
  duplicate: "Duplicada",
};

export const ESPECIALIDAD_SOURCE_LABELS: Record<string, string> = {
  label: "Etiqueta del informe",
  doctor_title: "Sello del médico",
  report_title: "Título del informe",
  fiscal_line: "Línea de la factura",
  auth_line: "Autorización",
  medico_primary: "Especialidad del médico",
  procedure: "Procedimiento",
  review: "Revisión",
};

export type MedicoListRow = {
  id: string;
  title: string | null;
  full_name: string;
  mpps: string | null;
  degree: string | null;
  especialidad: string | null;
  especialidad_code: string | null;
  area_name: string | null;
  atenciones: number;
  pacientes: number;
};

export type MedicoListFilters = {
  query: string;
  like: string;
  area: string;
  especialidad: string;
  hasMpps: "" | "1" | "0";
  pageSize: number;
  requestedPage: number;
};

export type EspecialidadOption = {
  code: string;
  name_es: string;
  level: number;
  parent_code: string | null;
  area_code: string;
  area_name: string;
};

export type AtencionRow = {
  id: string;
  encounter_date: string | Date | null;
  report_kind: string;
  link_status: string;
  especialidad: string | null;
  especialidad_source: string | null;
  procedimiento: string | null;
  medico_id: string | null;
  medico_name: string | null;
  medico_title: string | null;
  person_id: string | null;
  person_name: string | null;
  invoice_id: string | null;
  invoice_number: string | null;
  primary_document_id: string;
  diagnosis_text: string | null;
};

export type MedicoEspecialidadRow = {
  code: string;
  name_es: string;
  level: number;
  parent_name: string | null;
  area_name: string;
  source: string;
  evidence_count: number;
  is_primary: boolean;
};

export type MedicoPatientRow = {
  person_id: string;
  full_name: string | null;
  identity_number: string | null;
  especialidad: string | null;
  atenciones: number;
  last_seen: string | Date | null;
};

export type EspecialidadTreeRow = {
  id: string;
  code: string;
  name_es: string;
  level: number;
  parent_code: string | null;
  area_code: string;
  area_name: string;
  area_sort: number;
  marketing_category: string | null;
  atenciones: number;
  own_atenciones: number;
  medicos: number;
  procedimientos: number;
  terms: number;
};

export type EspecialidadBacklogRow = {
  l1_term: string;
  context: string;
  occurrences: number;
};

/** Area + especialidad options for filters, ordered as the taxonomy tree. */
export const listEspecialidadOptions = cache(async function listEspecialidadOptions(): Promise<
  EspecialidadOption[]
> {
  const db = sql();
  const rows = await db`
    SELECT code, name_es, level, parent_code, area_code, area_name
    FROM avila.v_especialidad_tree
    WHERE active
    ORDER BY area_sort, coalesce(parent_code, code), level, name_es
  `;
  return rows as EspecialidadOption[];
});

export async function queryMedicoList(filters: MedicoListFilters): Promise<{
  total: number;
  page: number;
  rows: MedicoListRow[];
}> {
  const { query, like, area, especialidad, hasMpps, pageSize, requestedPage } = filters;
  const db = sql();
  const [countRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.medico m
    WHERE m.merged_into IS NULL
      AND (${query} = '' OR m.full_name ILIKE ${like} OR coalesce(m.mpps, '') ILIKE ${like})
      AND (${hasMpps} = '' OR (${hasMpps} = '1' AND m.mpps IS NOT NULL) OR (${hasMpps} = '0' AND m.mpps IS NULL))
      AND (${especialidad} = '' OR EXISTS (
        SELECT 1 FROM avila.medico_especialidad me
        JOIN avila.especialidad e ON e.id = me.especialidad_id
        LEFT JOIN avila.especialidad pe ON pe.id = e.parent_id
        WHERE me.medico_id = m.id AND (e.code = ${especialidad} OR pe.code = ${especialidad})
      ))
      AND (${area} = '' OR EXISTS (
        SELECT 1 FROM avila.medico_especialidad me
        JOIN avila.especialidad e ON e.id = me.especialidad_id
        WHERE me.medico_id = m.id AND e.area_code = ${area}
      ))
  `;
  const total = countRow?.n ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  const offset = (page - 1) * pageSize;

  const rows = await db`
    SELECT m.id::text AS id, m.title, m.full_name, m.mpps, m.degree,
           pe.name_es AS especialidad, pe.code AS especialidad_code, ar.name_es AS area_name,
           coalesce(st.atenciones, 0)::int AS atenciones,
           coalesce(st.pacientes, 0)::int AS pacientes
    FROM avila.medico m
    LEFT JOIN avila.medico_especialidad mp ON mp.medico_id = m.id AND mp.is_primary
    LEFT JOIN avila.especialidad pe ON pe.id = mp.especialidad_id
    LEFT JOIN avila.especialidad_area ar ON ar.code = pe.area_code
    LEFT JOIN (
      SELECT medico_id, count(*)::int AS atenciones, count(DISTINCT person_id)::int AS pacientes
      FROM avila.atencion
      WHERE link_status <> 'duplicate'
      GROUP BY medico_id
    ) st ON st.medico_id = m.id
    WHERE m.merged_into IS NULL
      AND (${query} = '' OR m.full_name ILIKE ${like} OR coalesce(m.mpps, '') ILIKE ${like})
      AND (${hasMpps} = '' OR (${hasMpps} = '1' AND m.mpps IS NOT NULL) OR (${hasMpps} = '0' AND m.mpps IS NULL))
      AND (${especialidad} = '' OR EXISTS (
        SELECT 1 FROM avila.medico_especialidad me
        JOIN avila.especialidad e ON e.id = me.especialidad_id
        LEFT JOIN avila.especialidad ep ON ep.id = e.parent_id
        WHERE me.medico_id = m.id AND (e.code = ${especialidad} OR ep.code = ${especialidad})
      ))
      AND (${area} = '' OR EXISTS (
        SELECT 1 FROM avila.medico_especialidad me
        JOIN avila.especialidad e ON e.id = me.especialidad_id
        WHERE me.medico_id = m.id AND e.area_code = ${area}
      ))
    ORDER BY coalesce(st.atenciones, 0) DESC, lower(m.full_name)
    LIMIT ${pageSize} OFFSET ${offset}
  `;
  return { total, page, rows: rows as MedicoListRow[] };
}

/** Corpus KPIs for the médicos directory. */
export const getMedicoKpis = cache(async function getMedicoKpis() {
  const db = sql();
  const [row] = await db`
    SELECT
      count(*) FILTER (WHERE merged_into IS NULL)::int AS medicos,
      count(*) FILTER (WHERE merged_into IS NULL AND mpps IS NOT NULL)::int AS con_mpps,
      count(*) FILTER (WHERE merged_into IS NULL AND EXISTS (
        SELECT 1 FROM avila.medico_especialidad me WHERE me.medico_id = m.id AND me.is_primary
      ))::int AS con_especialidad
    FROM avila.medico m
  `;
  const [att] = await db`
    SELECT count(*)::int AS atenciones,
           count(*) FILTER (WHERE link_status = 'complete')::int AS completas
    FROM avila.atencion
    WHERE link_status <> 'duplicate'
  `;
  const [reviews] = await db`
    SELECT count(*)::int AS n FROM avila.review_item
    WHERE status = 'open' AND kind IN ('medico_duplicate', 'medico_mpps_conflict', 'atencion_patient', 'especialidad_unknown')
  `;
  return {
    medicos: row?.medicos ?? 0,
    conMpps: row?.con_mpps ?? 0,
    conEspecialidad: row?.con_especialidad ?? 0,
    atenciones: att?.atenciones ?? 0,
    completas: att?.completas ?? 0,
    openReviews: reviews?.n ?? 0,
  };
});

export type MedicoKpis = Awaited<ReturnType<typeof getMedicoKpis>>;

export type ClinicalStatusRow = { status: string; n: number };

/** Directory KPIs plus the especialidades and link statuses the informe shows. */
export async function getClinicalSummary() {
  const db = sql();
  const [kpis, top, statuses] = await Promise.all([
    getMedicoKpis(),
    db`
      SELECT code, name_es, area_name, atenciones, medicos
      FROM avila.v_especialidad_tree
      WHERE level = 1 AND atenciones > 0
      ORDER BY atenciones DESC, name_es
      LIMIT 10
    `,
    db`
      SELECT link_status AS status, count(*)::int AS n
      FROM avila.atencion
      GROUP BY link_status
      ORDER BY count(*) DESC
    `,
  ]);
  return {
    kpis,
    topEspecialidades: top as Pick<EspecialidadTreeRow, "code" | "name_es" | "area_name" | "atenciones" | "medicos">[],
    statuses: statuses as ClinicalStatusRow[],
  };
}

export type ClinicalSummary = Awaited<ReturnType<typeof getClinicalSummary>>;

export async function getMedicoDetail(id: string) {
  const db = sql();
  const [medico] = await db`
    SELECT id::text AS id, title, full_name, name_folded, degree, degree_university, mpps,
           colegio_number, rif, provisional_key, is_gps_staff, merged_into::text AS merged_into,
           created_at, updated_at
    FROM avila.medico WHERE id = ${id}::uuid
  `;
  if (!medico) return null;

  const especialidades = await db`
    SELECT e.code, e.name_es, e.level, pe.name_es AS parent_name, ar.name_es AS area_name,
           me.source, me.evidence_count, me.is_primary
    FROM avila.medico_especialidad me
    JOIN avila.especialidad e ON e.id = me.especialidad_id
    JOIN avila.especialidad_area ar ON ar.code = e.area_code
    LEFT JOIN avila.especialidad pe ON pe.id = e.parent_id
    WHERE me.medico_id = ${id}::uuid
    ORDER BY me.is_primary DESC, me.evidence_count DESC, e.name_es
  `;

  const [stats] = await db`
    SELECT count(*)::int AS atenciones,
           count(DISTINCT person_id)::int AS pacientes,
           count(DISTINCT invoice_id)::int AS facturas,
           min(encounter_date) AS first_seen,
           max(encounter_date) AS last_seen
    FROM avila.atencion
    WHERE medico_id = ${id}::uuid AND link_status <> 'duplicate'
  `;

  const patients = await db`
    SELECT v.person_id::text AS person_id, p.full_name, p.identity_number,
           e.name_es AS especialidad, v.atenciones, v.last_seen
    FROM avila.v_person_medico v
    JOIN avila.person p ON p.id = v.person_id
    LEFT JOIN avila.especialidad e ON e.id = v.especialidad_id
    WHERE v.medico_id = ${id}::uuid
    ORDER BY v.atenciones DESC, v.last_seen DESC NULLS LAST
    LIMIT ${MEDICO_PATIENT_LIMIT}
  `;

  const atenciones = await queryAtenciones({ medicoId: id, personId: "", invoiceId: "" });

  const [mentions] = await db`
    SELECT count(*)::int AS n FROM avila.medico_mention WHERE medico_id = ${id}::uuid
  `;
  const [reviews] = await db`
    SELECT count(*)::int AS n FROM avila.review_item
    WHERE status = 'open' AND (medico_id = ${id}::uuid OR other_medico_id = ${id}::uuid)
  `;

  return {
    medico,
    especialidades: especialidades as MedicoEspecialidadRow[],
    stats: {
      atenciones: stats?.atenciones ?? 0,
      pacientes: stats?.pacientes ?? 0,
      facturas: stats?.facturas ?? 0,
      firstSeen: (stats?.first_seen ?? null) as string | Date | null,
      lastSeen: (stats?.last_seen ?? null) as string | Date | null,
    },
    patients: patients as MedicoPatientRow[],
    atenciones,
    mentions: mentions?.n ?? 0,
    openReviews: reviews?.n ?? 0,
  };
}

export type MedicoDetail = NonNullable<Awaited<ReturnType<typeof getMedicoDetail>>>;

export async function getMedicoPageTitle(id: string): Promise<string | null> {
  const db = sql();
  const [row] = await db`SELECT full_name FROM avila.medico WHERE id = ${id}::uuid`;
  return row ? String(row.full_name) : null;
}

/** Atenciones for one médico, persona, or factura (duplicates excluded). */
export async function queryAtenciones(scope: {
  medicoId: string;
  personId: string;
  invoiceId: string;
}): Promise<AtencionRow[]> {
  const { medicoId, personId, invoiceId } = scope;
  if (!medicoId && !personId && !invoiceId) return [];
  const db = sql();
  const rows = await db`
    SELECT a.id::text AS id, a.encounter_date, a.report_kind, a.link_status,
           e.name_es AS especialidad, a.especialidad_source, pr.name_es AS procedimiento,
           coalesce(m.merged_into, m.id)::text AS medico_id, m.full_name AS medico_name, m.title AS medico_title,
           a.person_id::text AS person_id, p.full_name AS person_name,
           a.invoice_id::text AS invoice_id, i.invoice_number,
           a.primary_document_id::text AS primary_document_id, a.diagnosis_text
    FROM avila.atencion a
    LEFT JOIN avila.medico m ON m.id = a.medico_id
    LEFT JOIN avila.especialidad e ON e.id = a.especialidad_id
    LEFT JOIN avila.procedimiento pr ON pr.id = a.procedimiento_id
    LEFT JOIN avila.person p ON p.id = a.person_id
    LEFT JOIN avila.invoice i ON i.id = a.invoice_id
    WHERE a.link_status <> 'duplicate'
      AND (${medicoId} = '' OR coalesce(m.merged_into, m.id) = nullif(${medicoId}, '')::uuid)
      AND (${personId} = '' OR a.person_id = nullif(${personId}, '')::uuid)
      AND (${invoiceId} = '' OR a.invoice_id = nullif(${invoiceId}, '')::uuid)
    ORDER BY a.encounter_date DESC NULLS LAST, a.created_at DESC
    LIMIT ${MEDICO_ATENCION_LIMIT}
  `;
  return rows as AtencionRow[];
}

/** One row per médico the patient has seen, with especialidades and visit counts. */
export type PersonaMedicoRow = {
  medico_id: string;
  medico_name: string;
  medico_title: string | null;
  mpps: string | null;
  especialidades: string[];
  atenciones: number;
  first_seen: string | Date | null;
  last_seen: string | Date | null;
};

export async function getPersonaMedicos(personId: string): Promise<{
  medicos: PersonaMedicoRow[];
  atenciones: AtencionRow[];
}> {
  const db = sql();
  const medicos = await db`
    SELECT coalesce(m.merged_into, m.id)::text AS medico_id, m.full_name AS medico_name,
           m.title AS medico_title, m.mpps,
           array_remove(array_agg(DISTINCT e.name_es), NULL) AS especialidades,
           sum(v.atenciones)::int AS atenciones,
           min(v.first_seen) AS first_seen, max(v.last_seen) AS last_seen
    FROM avila.v_person_medico v
    JOIN avila.medico m ON m.id = v.medico_id
    LEFT JOIN avila.especialidad e ON e.id = v.especialidad_id
    WHERE v.person_id = ${personId}::uuid
    GROUP BY 1, 2, 3, 4
    ORDER BY sum(v.atenciones) DESC, max(v.last_seen) DESC NULLS LAST
  `;
  const atenciones = await queryAtenciones({ medicoId: "", personId, invoiceId: "" });
  return { medicos: medicos as PersonaMedicoRow[], atenciones };
}

export async function getEspecialidadTree(): Promise<EspecialidadTreeRow[]> {
  const db = sql();
  const rows = await db`
    SELECT id::text AS id, code, name_es, level, parent_code, area_code, area_name, area_sort,
           marketing_category, atenciones, own_atenciones, medicos, procedimientos, terms
    FROM avila.v_especialidad_tree
    WHERE active
    ORDER BY area_sort, coalesce(parent_code, code), level, name_es
  `;
  return rows as EspecialidadTreeRow[];
}

/** Terms seen on documents that matched no catalog entry (for the review backlog). */
export async function getEspecialidadBacklog(): Promise<{
  rows: EspecialidadBacklogRow[];
  observations: number;
  unknown: number;
  openReviews: number;
}> {
  const db = sql();
  const rows = await db`
    SELECT l1_term, context, count(*)::int AS occurrences
    FROM avila.especialidad_observation
    WHERE match_method = 'none'
    GROUP BY l1_term, context
    ORDER BY count(*) DESC, l1_term
    LIMIT ${ESPECIALIDAD_BACKLOG_LIMIT}
  `;
  const [totals] = await db`
    SELECT count(*)::int AS observations,
           count(*) FILTER (WHERE match_method = 'none')::int AS unknown
    FROM avila.especialidad_observation
  `;
  const [reviews] = await db`
    SELECT count(*)::int AS n FROM avila.review_item
    WHERE status = 'open' AND kind = 'especialidad_unknown'
  `;
  return {
    rows: rows as EspecialidadBacklogRow[],
    observations: totals?.observations ?? 0,
    unknown: totals?.unknown ?? 0,
    openReviews: reviews?.n ?? 0,
  };
}
