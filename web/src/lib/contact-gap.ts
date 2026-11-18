/** Spanish line under an empty contact field. Codes come from enrich_person_contact.py. */

export const CONTACT_GAP_COPY: Record<string, string> = {
  not_applicable_menor: "El teléfono y la dirección de un menor quedan en el titular.",
  no_candidate_page: "Este expediente no tiene cédula, acta ni planilla con ese dato.",
  ocr_no_cue: "Las páginas están leídas y no contienen ese dato.",
  unparsed: "El dato aparece en la página, pero la lectura no es una fecha, un teléfono o una dirección usable.",
  only_letterhead: "Solo aparecen teléfonos o direcciones de la clínica o la aseguradora.",
  ambiguous: "Hay un dato en la página, pero no corresponde a una sola persona.",
  conflict: "Hay otro valor distinto. Quedó en Revisión y no reemplazó el guardado.",
  blocked_review: "Este expediente tiene un conflicto de cédula abierto, así que no se atribuyó el dato.",
  junk: "Registro descartado.",
  no_invoice_documents: "Esta persona no tiene facturas ni páginas de donde leer el dato.",
  unsegmented_scan: "La página está en un lote del escáner que todavía no se puede asignar a una factura.",
  outside_ocr_scope: "El archivo en la copia de respaldo no es una factura, una cédula ni una planilla leída.",
};

export function contactGapCode(gap: unknown, field: "birth_date" | "phone" | "address"): string | undefined {
  if (!gap || typeof gap !== "object") return undefined;
  const code = (gap as Record<string, unknown>)[field];
  return typeof code === "string" && code !== "filled" ? code : undefined;
}
