/** Shared CSV table builders for list / Informe exports. */

export type CsvTable = {
  name: string;
  headers: string[];
  rows: (string | number)[][];
};

/** @deprecated Prefer `CsvTable`. Kept for Informe call sites. */
export type InformeCsvTable = CsvTable;

export function escapeCsv(value: string | number): string {
  const text = String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function buildCsv(tables: CsvTable[]): string {
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

export function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
