import { sql } from "@/lib/db";

export type ReviewKindCount = { kind: string; n: number };

export type ReviewQueueItem = {
  id: string;
  kind: string;
  status: string;
  score: number | string | null;
  evidence: unknown;
  created_at: string | Date | null;
  resolved_by: string | null;
  resolved_at: string | Date | null;
  person_id: string | null;
  p_name: string | null;
  p_ci: string | null;
  p_dob: string | Date | null;
  other_person_id: string | null;
  o_name: string | null;
  o_ci: string | null;
  o_dob: string | Date | null;
  invoice_id: string | null;
  invoice_number: string | null;
  issue_date: string | Date | null;
  document_id: string | null;
  document_type: string | null;
  blob_pathname: string | null;
  authorization_line_id: string | null;
  clave_rms: string | null;
  request_date: string | Date | null;
  service_description: string | null;
  medico_id: string | null;
  m_name: string | null;
  m_mpps: string | null;
  other_medico_id: string | null;
  om_name: string | null;
  om_mpps: string | null;
  atencion_id: string | null;
};

export async function queryReviewQueue(input: {
  status: string;
  kinds: string[];
  pageSize: number;
  requestedPage: number;
}): Promise<{ counts: ReviewKindCount[]; total: number; page: number; items: ReviewQueueItem[] }> {
  const { status, kinds, pageSize, requestedPage } = input;
  const db = sql();
  const counts = await db`
    SELECT kind, count(*)::int AS n FROM avila.review_item
    WHERE status = ${status} GROUP BY kind
  `;
  const byKind = new Map(
    (counts as ReviewKindCount[]).map((row) => [row.kind, row.n]),
  );
  const total = kinds.reduce((sum, kind) => sum + (byKind.get(kind) || 0), 0);
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  const page = Math.min(Math.max(1, requestedPage), totalPages);

  const items = await db`
    SELECT r.id, r.kind, r.status, r.score, r.evidence, r.created_at, r.resolved_by, r.resolved_at,
           r.person_id, p.full_name AS p_name, p.identity_number AS p_ci, p.birth_date AS p_dob,
           r.other_person_id, o.full_name AS o_name, o.identity_number AS o_ci, o.birth_date AS o_dob,
           r.invoice_id, i.invoice_number, i.issue_date,
           r.document_id, d.document_type, d.blob_pathname,
           r.authorization_line_id, al.clave_rms, al.request_date, al.service_description,
           r.medico_id, m.full_name AS m_name, m.mpps AS m_mpps,
           r.other_medico_id, om.full_name AS om_name, om.mpps AS om_mpps,
           r.atencion_id
    FROM avila.review_item r
    LEFT JOIN avila.medico m ON m.id = r.medico_id
    LEFT JOIN avila.medico om ON om.id = r.other_medico_id
    LEFT JOIN avila.person p ON p.id = r.person_id
    LEFT JOIN avila.person o ON o.id = r.other_person_id
    LEFT JOIN avila.invoice i ON i.id = r.invoice_id
    LEFT JOIN avila.document d ON d.id = r.document_id
    LEFT JOIN avila.authorization_line al ON al.id = r.authorization_line_id
    WHERE r.status = ${status} AND r.kind = ANY(${kinds})
    ORDER BY r.score DESC NULLS LAST, r.created_at DESC
    LIMIT ${pageSize} OFFSET ${(page - 1) * pageSize}
  `;

  return {
    counts: counts as ReviewKindCount[],
    total,
    page,
    items: items as ReviewQueueItem[],
  };
}
