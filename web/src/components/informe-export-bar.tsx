"use client";

import { Download, Printer } from "lucide-react";

export type InformeCsvTable = {
  name: string;
  headers: string[];
  rows: (string | number)[][];
};

function escapeCsv(value: string | number): string {
  const text = String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function buildCsv(tables: InformeCsvTable[]): string {
  const blocks = tables.map((table) => {
    const lines = [
      `# ${table.name}`,
      table.headers.map(escapeCsv).join(","),
      ...table.rows.map((row) => row.map(escapeCsv).join(",")),
    ];
    return lines.join("\n");
  });
  return blocks.join("\n\n");
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Print and CSV export for a single Informe inventory section (personas or facturas). */
export function InformeExportBar({
  section,
  rangeLabel,
  tables,
}: {
  /** Used in the CSV filename, e.g. `personas` or `facturas`. */
  section: "personas" | "facturas";
  rangeLabel: string;
  tables: InformeCsvTable[];
}) {
  return (
    <div className="informe-export-bar flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => window.print()}
        className="inline-flex min-h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
      >
        <Printer aria-hidden="true" className="size-4" />
        Imprimir
      </button>
      <button
        type="button"
        onClick={() => {
          const stamp = new Date().toISOString().slice(0, 10);
          downloadCsv(`avila-informe-${section}-${rangeLabel}-${stamp}.csv`, buildCsv(tables));
        }}
        className="inline-flex min-h-9 items-center gap-2 rounded-full border border-border bg-card px-3 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted"
      >
        <Download aria-hidden="true" className="size-4" />
        Exportar CSV
      </button>
    </div>
  );
}
