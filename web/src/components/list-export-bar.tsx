"use client";

import { Download, Printer } from "lucide-react";
import { buildCsv, downloadCsv, type CsvTable } from "@/lib/csv";

/** Print + CSV download for a filtered list or Informe inventory section. */
export function ListExportBar({
  filenamePrefix,
  tables,
  disabled = false,
  note,
}: {
  /** Filename stem without date or `.csv`, e.g. `avila-personas` or `avila-informe-personas-6m`. */
  filenamePrefix: string;
  tables: CsvTable[];
  disabled?: boolean;
  /** Optional hint, e.g. when the export is capped below the full match count. */
  note?: string;
}) {
  const empty = disabled || tables.every((t) => t.rows.length === 0);

  return (
    <div className="list-export-bar flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={empty}
        onClick={() => window.print()}
        className="inline-flex min-h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
      >
        <Printer aria-hidden="true" className="size-4" />
        Imprimir
      </button>
      <button
        type="button"
        disabled={empty}
        onClick={() => {
          const stamp = new Date().toISOString().slice(0, 10);
          downloadCsv(`${filenamePrefix}-${stamp}.csv`, buildCsv(tables));
        }}
        className="inline-flex min-h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
      >
        <Download aria-hidden="true" className="size-4" />
        Exportar CSV
      </button>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}
