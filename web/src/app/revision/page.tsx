import Link from "next/link";
import { DocumentPreview } from "@/components/document-preview";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Pagination, parsePage } from "@/components/pagination";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { buildListHref, firstParam } from "@/lib/list-params";
import { requirePermission } from "@/lib/auth";
import { queryReviewQueue, type ReviewQueueItem } from "@/lib/review-queue-data";
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
    <Link href={`/personas/${id}`} className="font-medium text-brand hover:underline">
      {name || "(sin nombre)"}
      {ci ? <span className="ml-1 text-xs text-muted-foreground">CI {ci}</span> : null}
    </Link>
  );
}

function MedicoLink({ id, name, mpps }: { id: string; name: string | null; mpps: string | null }) {
  return (
    <Link href={`/medicos/${id}`} className="font-medium text-brand hover:underline">
      {name || "(sin nombre)"}
      {mpps ? <span className="ml-1 text-xs text-muted-foreground">MPPS {mpps}</span> : null}
    </Link>
  );
}

const NO_CANDIDATE_NOTE =
  "Sin una persona sugerida. Abre la factura, identifica al paciente y rechaza este caso si el informe no es de esa factura.";

function needsCandidate(item: ReviewQueueItem): boolean {
  return item.kind === "atencion_patient" && !item.person_id;
}

export default async function RevisionPage({
  searchParams,
}: {
  searchParams: Promise<{ tipo?: string; estado?: string; page?: string }>;
}) {
  await requirePermission("review");
  const sp = await searchParams;
  const group = REVIEW_GROUPS.find((g) => g.id === firstParam(sp.tipo));
  const status = STATUSES[firstParam(sp.estado)] ? firstParam(sp.estado) : "open";
  const requestedPage = parsePage(firstParam(sp.page) || undefined);
  const kinds = group ? group.kinds : REVIEW_GROUPS.flatMap((g) => g.kinds);
  const { counts, total, page, items } = await queryReviewQueue({
    status,
    kinds,
    pageSize: PAGE_SIZE,
    requestedPage,
  });
  const byKind = new Map(counts.map((row) => [row.kind, row.n]));
  const groupCount = (k: string[]) => k.reduce((sum, kind) => sum + (byKind.get(kind) || 0), 0);

  const pill = (active: boolean) =>
    `rounded-full px-4 py-2 text-xs font-medium transition ${
      active
        ? "bg-hero text-white"
        : "border border-border bg-card text-muted-foreground hover:text-brand"
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
            <article key={item.id} className="rounded-3xl border border-border bg-card p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium tracking-wider text-info uppercase">
                    {REVIEW_KIND_LABELS[item.kind] || item.kind}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Detectado {formatDate(item.created_at)}
                    {item.score != null ? ` · confianza ${Number(item.score).toFixed(2)}` : ""}
                    {item.resolved_by ? ` · resuelto por ${item.resolved_by} el ${formatDate(item.resolved_at)}` : ""}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-[1fr_280px]">
                <div className="space-y-3 text-sm">
                  {item.person_id ? (
                    <div className="rounded-2xl bg-background p-3">
                      <PersonLink id={item.person_id} name={item.p_name} ci={item.p_ci} />
                      {item.p_dob ? (
                        <span className="ml-2 text-xs text-muted-foreground">nac. {formatDate(item.p_dob)}</span>
                      ) : null}
                      {item.other_person_id ? (
                        <div className="mt-2">
                          <PersonLink id={item.other_person_id} name={item.o_name} ci={item.o_ci} />
                          {item.o_dob ? (
                            <span className="ml-2 text-xs text-muted-foreground">nac. {formatDate(item.o_dob)}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {item.medico_id ? (
                    <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-2xl bg-background p-3">
                      <MedicoLink id={item.medico_id} name={item.m_name} mpps={item.m_mpps} />
                      {item.other_medico_id ? (
                        <MedicoLink id={item.other_medico_id} name={item.om_name} mpps={item.om_mpps} />
                      ) : null}
                    </div>
                  ) : null}
                  {item.invoice_id ? (
                    <p>
                      <Link href={`/facturas/${item.invoice_id}`} className="text-brand hover:underline">
                        {formatInvoiceNumber(item.invoice_number)}
                      </Link>
                      {item.issue_date ? (
                        <span className="ml-2 text-xs text-muted-foreground">emitida {formatDate(item.issue_date)}</span>
                      ) : null}
                    </p>
                  ) : null}
                  {item.authorization_line_id ? (
                    <p className="text-foreground/80">
                      Autorización {item.clave_rms || "sin clave"} · {formatDate(item.request_date)}
                      {item.service_description ? ` · ${item.service_description}` : ""}
                    </p>
                  ) : null}
                  {evidenceEntries(item.evidence).length ? (
                    <dl className="grid gap-1 text-xs sm:grid-cols-[160px_1fr]">
                      {evidenceEntries(item.evidence).map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt className="text-muted-foreground">{k}</dt>
                          <dd className="break-words text-foreground/80">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                  {item.status === "open" ? (
                    <p className="text-xs text-muted-foreground">
                      {needsCandidate(item) ? NO_CANDIDATE_NOTE : ACCEPT_EFFECT[item.kind]}
                    </p>
                  ) : null}
                </div>

                {item.document_id && item.blob_pathname ? (
                  <div className="overflow-hidden rounded-2xl border border-border">
                    <DocumentPreview
                      src={`/api/blob/${item.document_id}`}
                      alt={DOCUMENT_TYPE_LABELS[item.document_type || ""] || "Documento"}
                    />
                  </div>
                ) : null}
              </div>

              {item.status === "open" ? (
                <form action={resolveReview} className="mt-5 flex flex-wrap gap-2">
                  <input type="hidden" name="id" value={item.id} />
                  {needsCandidate(item) ? null : (
                    <button
                      type="submit"
                      name="decision"
                      value="accept"
                      className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
                    >
                      Aceptar
                    </button>
                  )}
                  <button
                    type="submit"
                    name="decision"
                    value="reject"
                    className="rounded-full border border-border bg-card px-5 py-2.5 text-xs font-medium text-foreground/80 hover:text-brand"
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
        shown={items.length}
        basePath="/revision"
        searchParams={params}
      />
    </div>
  );
}
