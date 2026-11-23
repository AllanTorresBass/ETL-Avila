import { EstudioFileList, type EstudioFileItem } from "@/components/estudio-file-list";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { ESTUDIO_SOURCE_LABELS, ESTUDIO_STATUS_LABELS, type EstudioLine } from "@/lib/estudio-data";

export interface EstudioListProps {
  rows: EstudioLine[];
  linkInvoice?: boolean;
  className?: string;
}

function toFileItem(row: EstudioLine, linkInvoice: boolean): EstudioFileItem {
  const badges = [];
  if (row.linkStatus === "review" || row.linkStatus === "unmatched") {
    badges.push(ESTUDIO_STATUS_LABELS[row.linkStatus] || row.linkStatus);
  }
  const when = row.issueDate ? formatDate(row.issueDate) : null;
  return {
    id: row.id,
    title: row.serviceLabel || row.procedimientoName || "Estudio",
    badges,
    invoiceHref: linkInvoice ? `/facturas/${row.invoiceId}` : undefined,
    documentId: row.documentId,
    pageLabel: row.pageIndex != null ? `Página ${row.pageIndex}` : null,
    canPreview: row.uploadStatus === "uploaded",
    meta: [
      ESTUDIO_SOURCE_LABELS[row.source] || row.source,
      row.familyLabel,
      linkInvoice && row.invoiceNumber ? formatInvoiceNumber(row.invoiceNumber) : null,
      when,
    ]
      .filter(Boolean)
      .join(" · "),
  };
}

export function EstudioList({ rows, linkInvoice = false, className }: EstudioListProps) {
  return <EstudioFileList items={rows.map((row) => toFileItem(row, linkInvoice))} className={className} />;
}
