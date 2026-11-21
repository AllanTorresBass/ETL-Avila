import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import {
  ESPECIALIDAD_SOURCE_LABELS,
  LINK_STATUS_LABELS,
  REPORT_KIND_LABELS,
  type AtencionRow,
} from "@/lib/medico-data";
import { cn } from "@/lib/utils";

export interface AtencionListProps {
  rows: AtencionRow[];
  /** Hide the link that points back to the page already on screen. */
  hide?: "medico" | "persona" | "factura";
  emptyTitle: string;
  emptyHint: string;
  className?: string;
}

const STATUS_TONE: Record<string, string> = {
  complete: "bg-success-soft text-success",
  review: "bg-warning-soft text-warning",
  unmatched: "bg-muted text-muted-foreground",
  partial: "bg-brand/10 text-brand",
};

function doctorLabel(row: AtencionRow): string {
  const prefix = row.medico_title === "dra" ? "Dra." : "Dr.";
  return `${prefix} ${row.medico_name}`;
}

export function AtencionList({ rows, hide, emptyTitle, emptyHint, className }: AtencionListProps) {
  if (rows.length === 0) return <EmptyState title={emptyTitle} hint={emptyHint} />;

  return (
    <ul className={cn("space-y-2", className)}>
      {rows.map((row) => (
        <li key={row.id} className="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-hero px-2.5 py-0.5 text-[11px] font-medium text-white">
                {REPORT_KIND_LABELS[row.report_kind] || row.report_kind}
              </span>
              {row.especialidad ? (
                <span
                  className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[11px] font-medium text-brand"
                  title={row.especialidad_source ? ESPECIALIDAD_SOURCE_LABELS[row.especialidad_source] : undefined}
                >
                  {row.especialidad}
                </span>
              ) : null}
              {row.procedimiento ? (
                <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                  {row.procedimiento}
                </span>
              ) : null}
              <span
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-[11px] font-medium",
                  STATUS_TONE[row.link_status] || "bg-muted text-muted-foreground",
                )}
              >
                {LINK_STATUS_LABELS[row.link_status] || row.link_status}
              </span>
            </div>
            <span className="text-xs tabular-nums text-muted-foreground">
              {row.encounter_date ? formatDate(row.encounter_date) : "Sin fecha"}
            </span>
          </div>
          {row.diagnosis_text ? (
            <p className="mt-1.5 line-clamp-2 text-muted-foreground">{row.diagnosis_text}</p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {hide !== "medico" && row.medico_id && row.medico_name ? (
              <Link href={`/medicos/${row.medico_id}`} className="font-medium text-brand">
                {doctorLabel(row)}
              </Link>
            ) : null}
            {hide !== "persona" && row.person_id ? (
              <Link href={`/personas/${row.person_id}`} className="font-medium text-brand">
                {row.person_name || "Paciente"}
              </Link>
            ) : null}
            {hide !== "factura" && row.invoice_id ? (
              <Link href={`/facturas/${row.invoice_id}`} className="text-brand">
                {formatInvoiceNumber(row.invoice_number)}
              </Link>
            ) : null}
            <Link href={`/documentos/${row.primary_document_id}`} className="text-brand">
              Ver documento
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}
