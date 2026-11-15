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
