import { EntityRow } from "@/components/entity-row";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { ESTUDIO_SOURCE_LABELS, ESTUDIO_STATUS_LABELS, type EstudioLine } from "@/lib/estudio-data";

export function EstudioList({ rows, linkInvoice = false }: { rows: EstudioLine[]; linkInvoice?: boolean }) {
  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const badges = [];
        if (row.linkStatus === "review" || row.linkStatus === "unmatched") {
          badges.push(ESTUDIO_STATUS_LABELS[row.linkStatus] || row.linkStatus);
        }
        const when = row.issueDate ? formatDate(row.issueDate) : null;
        return (
          <EntityRow
            key={row.id}
            href={linkInvoice ? `/facturas/${row.invoiceId}` : undefined}
            title={row.procedimientoName || row.serviceLabel}
            badges={badges}
            meta={[
              ESTUDIO_SOURCE_LABELS[row.source] || row.source,
              row.familyLabel,
              linkInvoice && row.invoiceNumber ? formatInvoiceNumber(row.invoiceNumber) : null,
              when,
            ]
              .filter(Boolean)
              .join(" · ")}
          />
        );
      })}
    </div>
  );
}
