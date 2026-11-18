export const REVIEW_KIND_LABELS: Record<string, string> = {
  duplicate_candidate: "Posible duplicado",
  ci_conflict: "Conflicto de CI",
  workbook_titular: "Titular de sábana protegido",
  multiple_ci: "Varias cédulas en la página",
  acta_titular: "Titular tomado de un acta",
  dob_conflict: "Fecha de nacimiento distinta",
  phone_conflict: "Teléfono distinto",
  address_conflict: "Dirección distinta",
  auth_match: "Autorización sin factura",
  segment_review: "Paquete escaneado",
};

/** Filter pills: one pill can cover several kinds. */
export const REVIEW_GROUPS: { id: string; label: string; kinds: string[] }[] = [
  { id: "duplicado", label: "Duplicado", kinds: ["duplicate_candidate"] },
  {
    id: "ci",
    label: "Conflicto de CI",
    kinds: ["ci_conflict", "workbook_titular", "multiple_ci", "acta_titular"],
  },
  {
    id: "contacto",
    label: "Contacto",
    kinds: ["dob_conflict", "phone_conflict", "address_conflict"],
  },
  { id: "autorizacion", label: "Autorización sin factura", kinds: ["auth_match"] },
  { id: "paquete", label: "Paquete escaneado", kinds: ["segment_review"] },
];

/** What “Aceptar” does for each kind (shown on the card so the reviewer knows). */
export const ACCEPT_EFFECT: Record<string, string> = {
  duplicate_candidate: "Aceptar fusiona la segunda persona en la primera.",
  ci_conflict: "Aceptar hace titular a la persona de la cédula y deja al anterior como beneficiario.",
  workbook_titular: "Aceptar hace titular a la persona de la cédula y deja al anterior como beneficiario.",
  auth_match: "Aceptar vincula la autorización con la factura y, si falta, enlaza a la persona como beneficiario.",
  multiple_ci: "Aceptar marca la página como revisada; el titular no cambia.",
  acta_titular: "Aceptar confirma que el titular del acta no era el asegurado.",
  dob_conflict: "Aceptar confirma la fecha guardada; la otra fuente se ignora.",
  phone_conflict: "Aceptar confirma el teléfono guardado; la otra fuente se ignora.",
  address_conflict: "Aceptar confirma la dirección guardada; la otra fuente se ignora.",
  segment_review: "Aceptar marca el paquete como revisado para la próxima carga.",
};

export const SOURCE_KIND_LABELS: Record<string, string> = {
  workbook: "Sábana",
  ocr: "OCR",
  path: "Ruta del archivo",
  case_evidence: "Caso revisado",
  manual: "Manual",
  review: "Revisión",
  derived: "Derivado",
};

export const FIELD_LABELS: Record<string, string> = {
  full_name: "Nombre",
  birth_date: "Nacimiento",
  phone: "Teléfono",
  address: "Dirección",
  identity_number: "Cédula",
  merged_from: "Fusión",
  role: "Rol en factura",
  document_type: "Tipo de documento",
  invoice_id: "Factura",
};
