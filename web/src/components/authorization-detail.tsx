import Link from "next/link";
import { linkAuthorization, unlinkAuthorizationAction } from "@/app/autorizaciones/actions";
import { AuthorizationStatusPill } from "@/components/authorization-status-pill";
import { EmptyState } from "@/components/empty-state";
import { KpiCard } from "@/components/kpi-card";
import { SectionCard } from "@/components/section-card";
import type { AuthPersonRef, AuthorizationDetail } from "@/lib/authorization-data";
import {
  AUTH_DATE_SOURCE_LABELS,
  AUTH_RULE_LABELS,
  AUTH_STATUS_HINTS,
  AUTH_VIA_LABELS,
  SOURCE_KIND_LABELS,
  authReasonLabel,
  authSignalLabel,
} from "@/lib/authorization-labels";
import { formatAuthDate, formatDate, formatInvoiceNumber, formatMoney, roleLabel } from "@/lib/format";
import { formatDateTime } from "@/lib/format-metrics";
import { REVIEW_KIND_LABELS } from "@/lib/review";

const REVIEW_STATUS_LABELS: Record<string, string> = {
  open: "Abierta",
  accepted: "Aceptada",
  rejected: "Rechazada",
};

function text(value: unknown): string {
  if (value == null) return "";
  return String(value).trim();
}

function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="break-words font-medium text-foreground">{value || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

function gapLabel(days: number | null): string {
  if (days == null) return "Sin fecha para comparar";
  if (days < 0) return `${Math.abs(days)} días antes de la autorización`;
  if (days === 0) return "El mismo día";
  return `${days} días después`;
}

export function AuthorizationDetailView({
  detail,
  canReview,
}: {
  detail: AuthorizationDetail;
  canReview: boolean;
}) {
  const { line, person, titular, items, sources, copies, reviews, history, candidates } = detail;
  const status = text(line.match_status) || null;
  const invoiceId = text(line.invoice_id) || null;
  const signals = Array.isArray(line.match_signals) ? (line.match_signals as string[]) : [];
  const dateSource = text(line.date_source);
  const peopleRows = [
    person ? { who: "Paciente", ref: person } : null,
    titular && titular.id !== person?.id ? { who: "Titular", ref: titular } : null,
  ].filter((p): p is { who: string; ref: AuthPersonRef } => p !== null);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard featured label="Solicitado USD" value={formatMoney(line.amount_usd)} hint={`BS ${formatMoney(line.amount_bs)}`} />
        <KpiCard label="Cobertura" value={formatMoney(line.coverage_amount)} />
        <KpiCard label="Autorizado" value={formatMoney(line.authorized_amount)} />
        <KpiCard
          label="Fecha"
          value={formatAuthDate(line)}
          hint={dateSource ? AUTH_DATE_SOURCE_LABELS[dateSource] ?? dateSource : "Sin fecha en el libro"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Resumen" description="Lo que dice la fila del libro, ya normalizado.">
          <Facts
            rows={[
              ["Aseguradora", text(line.account_name)],
              ["Contratante", text(line.contratante)],
              ["Proveedor", text(line.provider_name)],
              ["Especialidad", text(line.especialidad)],
              ["Procedimiento", text(line.procedimiento)],
              ["Clave RMS", text(line.clave_rms)],
              ["Código APS", text(line.aps_code)],
              ["Fecha de solicitud", line.request_date ? formatDate(line.request_date) : ""],
              ["Fecha de servicio", line.service_date ? formatDate(line.service_date) : ""],
              ["Diagnóstico", text(line.diagnosis)],
            ]}
          />
          {text(line.service_description) ? (
            <p className="mt-4 text-sm text-muted-foreground">{text(line.service_description)}</p>
          ) : null}
        </SectionCard>

        <SectionCard title="Paciente y titular" description="Personas que la línea identifica.">
          {peopleRows.length > 0 ? (
            <ul className="space-y-2">
              {peopleRows.map(({ who, ref }) => (
                <li key={who}>
                  <Link
                    href={`/personas/${ref.id}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-sm transition hover:border-brand/40"
                  >
                    <span className="font-medium text-brand">{ref.full_name || "Sin nombre"}</span>
                    <span className="text-xs text-muted-foreground">
                      {who}
                      {ref.identity_number ? ` · ${ref.identity_number}` : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">La línea no identifica paciente ni titular.</p>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Ítems" description="Consultas, estudios y servicios que cubre la autorización.">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">El libro no detalla ítems para esta línea.</p>
        ) : (
          <ul className="divide-y divide-border text-sm">
            {items.map((item) => (
              <li key={item.position} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                <span className="font-medium text-foreground">{item.label}</span>
                <span className="text-xs text-muted-foreground">
                  {item.kind}
                  {item.quantity != null ? ` · × ${item.quantity}` : ""}
                  {item.source_row ? ` · fila ${item.source_row}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Factura"
        description={status ? AUTH_STATUS_HINTS[status] : "El emparejador aún no evaluó esta línea."}
        action={<AuthorizationStatusPill status={status} invoiceId={invoiceId} />}
      >
        <div className="space-y-4">
          {invoiceId ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-sm">
              <div>
                <Link href={`/facturas/${invoiceId}`} className="font-medium text-brand hover:underline">
                  {formatInvoiceNumber(text(line.invoice_number))}
                </Link>
                <p className="text-xs text-muted-foreground">
                  Emitida {formatDate(line.invoice_issue_date)} · USD {formatMoney(line.invoice_total_usd)}
                </p>
              </div>
              {canReview ? (
                <form action={unlinkAuthorizationAction}>
                  <input type="hidden" name="id" value={text(line.id)} />
                  <button
                    type="submit"
                    className="rounded-full border border-border bg-card px-5 py-2.5 text-xs font-medium text-foreground/80 hover:text-brand"
                  >
                    Desvincular
                  </button>
                </form>
              ) : null}
            </div>
          ) : null}

          {signals.length > 0 || line.match_score != null ? (
            <div className="space-y-1.5">
              <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                Mejor candidata del emparejador
                {line.match_score != null ? ` · puntaje ${Number(line.match_score).toFixed(2)}` : ""}
                {line.matched_at ? ` · ${formatDateTime(line.matched_at)}` : ""}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {signals.map((s) => (
                  <span key={s} className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {authSignalLabel(s)}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
              {invoiceId ? "Otras facturas posibles" : "Facturas posibles"}
            </p>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Ni el paciente ni el titular tienen otras facturas en esta aseguradora, y ninguna comparte la clave.
              </p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((c) => (
                  <li
                    key={c.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-sm"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link href={`/facturas/${c.id}`} className="font-medium text-brand hover:underline">
                          {formatInvoiceNumber(c.invoice_number)}
                        </Link>
                        {c.suggested ? (
                          <span className="rounded-full bg-warning-soft px-2.5 py-0.5 text-[11px] font-medium text-warning">
                            Sugerida
                          </span>
                        ) : null}
                        <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                          {AUTH_VIA_LABELS[c.via] ?? c.via}
                          {c.role ? ` · ${roleLabel(c.role)}` : ""}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Emitida {formatDate(c.issue_date)} · {gapLabel(c.gap_days)} · USD {formatMoney(c.total_usd)}
                        {c.account_name ? ` · ${c.account_name}` : ""}
                      </p>
                    </div>
                    {canReview ? (
                      <form action={linkAuthorization}>
                        <input type="hidden" name="id" value={text(line.id)} />
                        <input type="hidden" name="invoice_id" value={c.id} />
                        <button
                          type="submit"
                          className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
                        >
                          Vincular
                        </button>
                      </form>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Origen" description="Libro y fila de donde se cargó la línea.">
          <Facts
            rows={[
              ["Archivo", text(line.source_file)],
              ["Hoja y fila", text(line.source_row)],
              ["Cargada", formatDateTime(line.created_at)],
              ["Última actualización", formatDateTime(line.updated_at)],
            ]}
          />
          {sources.length > 1 ? (
            <div className="mt-4 space-y-1.5">
              <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                También aparece en
              </p>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {sources.map((s) => (
                  <li key={`${s.source_file}#${s.source_row}`} className="break-words">
                    {s.source_file}
                    {s.source_row ? ` · ${s.source_row}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {copies.length > 0 ? (
            <div className="mt-4 space-y-1.5">
              <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">Copias duplicadas</p>
              <ul className="space-y-1 text-xs">
                {copies.map((c) => (
                  <li key={c.id}>
                    <Link href={`/autorizaciones/${c.id}`} className="text-brand hover:underline">
                      {c.source_file || "Copia"}
                      {c.source_row ? ` · ${c.source_row}` : ""}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {line.duplicate_of ? (
            <p className="mt-4 text-sm">
              Esta línea copia otra solicitud:{" "}
              <Link href={`/autorizaciones/${text(line.duplicate_of)}`} className="text-brand hover:underline">
                ver la original
              </Link>
            </p>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Revisión"
          description="Casos abiertos o resueltos sobre esta línea."
          action={
            <Link href="/revision?tipo=autorizacion" className="text-xs font-medium text-brand hover:underline">
              Ir a Revisión
            </Link>
          }
        >
          {reviews.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin casos de revisión.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {reviews.map((r) => (
                <li key={r.id} className="rounded-2xl border border-border bg-card px-4 py-3 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{REVIEW_KIND_LABELS[r.kind] ?? r.kind}</span>
                    <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {REVIEW_STATUS_LABELS[r.status] ?? r.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {r.invoice_id ? `${formatInvoiceNumber(r.invoice_number)} · ` : ""}
                    {r.score != null ? `puntaje ${r.score.toFixed(2)} · ` : ""}
                    abierta {formatDateTime(r.created_at)}
                    {r.resolved_at ? ` · resuelta ${formatDateTime(r.resolved_at)}` : ""}
                    {r.resolved_by ? ` por ${r.resolved_by}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Historial"
        description="Cada cambio con su regla (cómo), su fecha y corrida (cuándo), su fuente (dónde) y su motivo (por qué)."
      >
        {history.length === 0 ? (
          <EmptyState title="Sin cambios registrados" hint="La línea conserva los valores de la primera carga." />
        ) : (
          <ol className="space-y-3 border-l border-border pl-4 text-sm">
            {history.map((h) => (
              <li key={h.id} className="relative">
                <span aria-hidden="true" className="absolute -left-[21px] top-1.5 size-2.5 rounded-full bg-brand" />
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-foreground">
                    {AUTH_RULE_LABELS[h.rule_id] ?? h.rule_id}
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {h.entity === "authorization_line" ? h.field : `${h.entity.replace("authorization_", "")}.${h.field}`}
                    </span>
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">{formatDateTime(h.created_at)}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {SOURCE_KIND_LABELS[h.source_kind] ?? h.source_kind}
                  {h.script ? ` · ${h.script}${h.mode ? ` (${h.mode})` : ""}` : ""}
                  {h.source_ref ? ` · ${h.source_ref}` : ""}
                  {h.confidence != null ? ` · confianza ${h.confidence.toFixed(2)}` : ""}
                </p>
                {h.reason ? <p className="text-xs text-foreground/80">{authReasonLabel(h.reason)}</p> : null}
              </li>
            ))}
          </ol>
        )}
      </SectionCard>
    </div>
  );
}
