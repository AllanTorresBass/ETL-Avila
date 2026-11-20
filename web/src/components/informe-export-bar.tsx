"use client";

import { ListExportBar } from "@/components/list-export-bar";
import type { CsvTable } from "@/lib/csv";

export type { CsvTable as InformeCsvTable } from "@/lib/csv";

/** Print and CSV export for a single Informe inventory section (personas or facturas). */
export function InformeExportBar({
  section,
  rangeLabel,
  tables,
}: {
  /** Used in the CSV filename, e.g. `personas` or `facturas`. */
  section: "personas" | "facturas";
  rangeLabel: string;
  tables: CsvTable[];
}) {
  return (
    <ListExportBar
      filenamePrefix={`avila-informe-${section}-${rangeLabel}`}
      tables={tables}
    />
  );
}
