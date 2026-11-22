import { IDENTITY_TYPE_LABELS, ROLE_LABELS } from "./db";

export function formatInvoiceNumber(invoiceNumber: string | null | undefined): string {
  if (!invoiceNumber) return "—";
  if (invoiceNumber.startsWith("range:")) {
    return `Rango ${invoiceNumber.slice("range:".length).replace(/_/g, "–")}`;
  }
  if (invoiceNumber.startsWith("path:")) {
    return `Sin FACT (${invoiceNumber.slice(5, 13)}…)`;
  }
  return `FACT ${invoiceNumber}`;
}

export function formatAccount(name: string | null | undefined): string {
  return name?.trim() ? name : "(sin cuenta)";
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? value.slice(0, 10) : value.toISOString().slice(0, 10);
  return d;
}

const MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"] as const;

function calendarParts(value: string | Date): { year: number; month: number; day: number } | null {
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return null;
    return { year: value.getFullYear(), month: value.getMonth() + 1, day: value.getDate() };
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

/** Calendar date in Spanish, with the year. Uses the date's own day, not a shifted UTC day. */
export function formatDateEs(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const parts = calendarParts(value);
  const month = parts ? MONTHS_ES[parts.month - 1] : undefined;
  if (!parts || !month) return "—";
  return `${parts.day} ${month} ${parts.year}`;
}

/** Month only, for authorizations dated by their workbook period: "mar 2023". */
export function formatMonthEs(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const parts = calendarParts(value);
  const month = parts ? MONTHS_ES[parts.month - 1] : undefined;
  if (!parts || !month) return "—";
  return `${month} ${parts.year}`;
}

/** Exact authorization date, else its period month, else a dash. */
export function formatAuthDate(line: {
  service_date?: string | Date | null;
  request_date?: string | Date | null;
  period_month?: string | Date | null;
}): string {
  const exact = line.service_date || line.request_date;
  if (exact) return formatDate(exact);
  if (line.period_month) return `Mes ${formatMonthEs(line.period_month)}`;
  return "Sin fecha";
}

/** Identity line for a person card. Empty number reads as missing cédula. */
export function formatIdentity(type: string | null | undefined, number: string | null | undefined): string {
  const id = number?.trim();
  if (!id) return "Sin cédula";
  if (type === "cedula" || type === "pasaporte" || type === "rif") {
    return `${IDENTITY_TYPE_LABELS[type]} ${id}`;
  }
  return `Documento ${id}`;
}

export function formatFacturaCount(count: number): string {
  return count === 1 ? "1 factura" : `${count.toLocaleString("es-VE")} facturas`;
}

export function formatDocumentCount(count: number): string {
  if (count === 0) return "Sin documentos";
  if (count === 1) return "1 documento";
  return `${count.toLocaleString("es-VE")} documentos`;
}

export function formatMoney(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-VE", { maximumFractionDigits: 2 });
}

export function roleLabel(role: string | null | undefined): string {
  if (!role) return ROLE_LABELS.unknown;
  return ROLE_LABELS[role] || ROLE_LABELS.unknown;
}

/** Prefer the backup basename; fall back to label + extension (scan packets are all "invoice_packet"). */
export function formatSourceFileTitle(
  backupPath: string | null | undefined,
  fileLabel: string | null | undefined,
  extension: string | null | undefined,
): string {
  const base = backupPath?.split(/[/\\]/).pop()?.trim();
  if (base) return base;
  const label = (fileLabel || "archivo").trim();
  const ext = (extension || "").trim();
  if (!ext) return label;
  if (label.toLowerCase().endsWith(ext.toLowerCase())) return label;
  return `${label}${ext.startsWith(".") ? " " : " "}${ext}`.replace(/\s+/g, " ").trim();
}

export function formatSourcePages(pages: number | null | undefined): string {
  return pages != null ? `${pages} pág` : "? pág";
}

export type AuthItemView = {
  label: string;
  quantity: string | number | null;
};

export function authItems(value: unknown): AuthItemView[] {
  let raw = value;
  if (typeof raw === "string") {
    try {
      raw = JSON.parse(raw) as unknown;
    } catch {
      return [];
    }
  }
  if (!Array.isArray(raw)) return [];
  const items: AuthItemView[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const label = (row as { label?: unknown }).label;
    if (typeof label !== "string" || !label.trim()) continue;
    const quantity = (row as { quantity?: unknown }).quantity;
    items.push({
      label,
      quantity: typeof quantity === "string" || typeof quantity === "number" ? quantity : null,
    });
  }
  return items;
}

export function formatAuthHeading(line: {
  aps_code?: string | null;
  clave_rms?: string | null;
}): string {
  const aps = line.aps_code?.trim();
  if (aps) return aps;
  const clave = line.clave_rms?.trim();
  return clave || "Sin clave";
}

export function formatAuthItem(item: AuthItemView): string {
  const quantity = item.quantity;
  if (quantity === null || quantity === "") return item.label;
  const number = typeof quantity === "number" ? quantity : Number(quantity);
  if (!Number.isFinite(number) || number <= 0) return item.label;
  const shown = Number.isInteger(number) ? String(number) : String(number);
  return `${item.label} × ${shown}`;
}
