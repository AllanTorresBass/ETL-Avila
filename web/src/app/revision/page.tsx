import Link from "next/link";
import { DocumentPreview } from "@/components/document-preview";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Pagination, parsePage } from "@/components/pagination";
import { DOCUMENT_TYPE_LABELS, sql } from "@/lib/db";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { buildListHref, firstParam } from "@/lib/list-params";
import { ACCEPT_EFFECT, REVIEW_GROUPS, REVIEW_KIND_LABELS } from "@/lib/review";
import { resolveReview } from "./actions";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;
const STATUSES: Record<string, string> = {
  open: "Abiertos",
  accepted: "Aceptados",
  rejected: "Rechazados",
};

function evidenceEntries(evidence: unknown): [string, string][] {
  if (!evidence || typeof evidence !== "object") return [];
  return Object.entries(evidence as Record<string, unknown>)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => {
      const text = typeof v === "string" ? v : JSON.stringify(v);
      return [k, text.length > 140 ? `${text.slice(0, 140)}…` : text];
    });
}

function PersonLink({ id, name, ci }: { id: string | null; name: string | null; ci: string | null }) {
  if (!id) return null;
  return (
    <Link href={`/personas/${id}`} className="font-medium text-[#033CA0] hover:underline">
      {name || "(sin nombre)"}
      {ci ? <span className="ml-1 text-xs text-slate-500">CI {ci}</span> : null}
    </Link>
  );
}

export default async function RevisionPage({
  searchParams,
}: {
  searchParams: Promise<{ tipo?: string; estado?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const group = REVIEW_GROUPS.find((g) => g.id === firstParam(sp.tipo));
  const status = STATUSES[firstParam(sp.estado)] ? firstParam(sp.estado) : "open";
  const page = parsePage(firstParam(sp.page) || undefined);
  const kinds = group ? group.kinds : REVIEW_GROUPS.flatMap((g) => g.kinds);
  const db = sql();

  const counts = await db`
    SELECT kind, count(*)::int AS n FROM avila.review_item
    WHERE status = ${status} GROUP BY kind
  `;
  const byKind = new Map(counts.map((r) => [r.kind as string, r.n as number]));
  const groupCount = (k: string[]) => k.reduce((sum, kind) => sum + (byKind.get(kind) || 0), 0);
  const total = groupCount(kinds);

  const items = await db`
    SELECT r.id, r.kind, r.status, r.score, r.evidence, r.created_at, r.resolved_by, r.resolved_at,
           r.person_id, p.full_name AS p_name, p.identity_number AS p_ci, p.birth_date AS p_dob,
           r.other_person_id, o.full_name AS o_name, o.identity_number AS o_ci, o.birth_date AS o_dob,
           r.invoice_id, i.invoice_number, i.issue_date,
           r.document_id, d.document_type, d.blob_pathname,
           r.authorization_line_id, al.clave_rms, al.request_date, al.service_description
    FROM avila.review_item r
    LEFT JOIN avila.person p ON p.id = r.person_id
    LEFT JOIN avila.person o ON o.id = r.other_person_id
    LEFT JOIN avila.invoice i ON i.id = r.invoice_id
    LEFT JOIN avila.document d ON d.id = r.document_id
    LEFT JOIN avila.authorization_line al ON al.id = r.authorization_line_id
    WHERE r.status = ${status} AND r.kind = ANY(${kinds})
    ORDER BY r.score DESC NULLS LAST, r.created_at DESC
    LIMIT ${PAGE_SIZE} OFFSET ${(page - 1) * PAGE_SIZE}
  `;

  const pill = (active: boolean) =>
    `rounded-full px-4 py-2 text-xs font-medium transition ${
      active
        ? "bg-[#0A2A6B] text-white"
        : "border border-slate-200 bg-white text-slate-600 hover:text-[#033CA0]"
    }`;
  const params = { tipo: group?.id, estado: status === "open" ? undefined : status };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cola de revisión"
        title="Revisión"
        description="Casos que el ETL no resolvió solo. Cada decisión queda registrada con su procedencia."
      />

      <div className="flex flex-wrap gap-2" aria-label="Tipo">
        <Link href={buildListHref("/revision", { ...params, tipo: undefined })} className={pill(!group)}>
          Todos · {groupCount(REVIEW_GROUPS.flatMap((g) => g.kinds))}
        </Link>
        {REVIEW_GROUPS.map((g) => (
          <Link
            key={g.id}
            href={buildListHref("/revision", { ...params, tipo: g.id })}
            className={pill(group?.id === g.id)}
          >
            {g.label} · {groupCount(g.kinds)}
          </Link>
        ))}
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Estado">
        {Object.entries(STATUSES).map(([key, label]) => (
          <Link
            key={key}
            href={buildListHref("/revision", { ...params, estado: key === "open" ? undefined : key })}
            className={pill(status === key)}
          >
            {label}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title={status === "open" ? "No hay casos pendientes" : "No hay casos en este estado"}
          hint="Los casos aparecen aquí cuando el resolvedor, el cotejo de autorizaciones o la carga de escaneos encuentran algo dudoso."
        />
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <article key={item.id} className="rounded-3xl border border-slate-100 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">
                    {REVIEW_KIND_LABELS[item.kind] || item.kind}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Detectado {formatDate(item.created_at)}
                    {item.score != null ? ` · confianza ${Number(item.score).toFixed(2)}` : ""}
                    {item.resolved_by ? ` · resuelto por ${item.resolved_by} el ${formatDate(item.resolved_at)}` : ""}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-[1fr_280px]">
                <div className="space-y-3 text-sm">
                  {item.person_id ? (
                    <div className="rounded-2xl bg-[#F4F8FC] p-3">
                      <PersonLink id={item.person_id} name={item.p_name} ci={item.p_ci} />
                      {item.p_dob ? (
                        <span className="ml-2 text-xs text-slate-500">nac. {formatDate(item.p_dob)}</span>
                      ) : null}
                      {item.other_person_id ? (
                        <div className="mt-2">
                          <PersonLink id={item.other_person_id} name={item.o_name} ci={item.o_ci} />
                          {item.o_dob ? (
                            <span className="ml-2 text-xs text-slate-500">nac. {formatDate(item.o_dob)}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {item.invoice_id ? (
                    <p>
                      <Link href={`/facturas/${item.invoice_id}`} className="text-[#033CA0] hover:underline">
                        {formatInvoiceNumber(item.invoice_number)}
                      </Link>
                      {item.issue_date ? (
                        <span className="ml-2 text-xs text-slate-500">emitida {formatDate(item.issue_date)}</span>
                      ) : null}
                    </p>
                  ) : null}
                  {item.authorization_line_id ? (
                    <p className="text-slate-700">
                      Autorización {item.clave_rms || "sin clave"} · {formatDate(item.request_date)}
                      {item.service_description ? ` · ${item.service_description}` : ""}
                    </p>
                  ) : null}
                  {evidenceEntries(item.evidence).length ? (
                    <dl className="grid gap-1 text-xs sm:grid-cols-[160px_1fr]">
                      {evidenceEntries(item.evidence).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-slate-500">{k}</dt>
                          <dd className="break-words text-slate-700">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                  {item.status === "open" ? (
                    <p className="text-xs text-slate-500">{ACCEPT_EFFECT[item.kind]}</p>
                  ) : null}
                </div>

                {item.document_id && item.blob_pathname ? (
                  <div className="overflow-hidden rounded-2xl border border-slate-100">
                    <DocumentPreview
                      src={`/api/blob/${item.document_id}`}
                      alt={DOCUMENT_TYPE_LABELS[item.document_type] || "Documento"}
                    />
                  </div>
                ) : null}
              </div>

              {item.status === "open" ? (
                <form action={resolveReview} className="mt-5 flex flex-wrap gap-2">
                  <input type="hidden" name="id" value={item.id} />
                  <button
                    type="submit"
                    name="decision"
                    value="accept"
                    className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
                  >
                    Aceptar
                  </button>
                  <button
                    type="submit"
                    name="decision"
                    value="reject"
                    className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-xs font-medium text-slate-700 hover:text-[#033CA0]"
                  >
                    Rechazar
                  </button>
                </form>
              ) : null}
            </article>
          ))}
        </div>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        basePath="/revision"
        searchParams={params}
      />
    </div>
  );
}
