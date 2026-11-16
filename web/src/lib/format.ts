import { ROLE_LABELS } from "./db";

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
