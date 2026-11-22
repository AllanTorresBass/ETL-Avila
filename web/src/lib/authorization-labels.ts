/** Labels for authorization lines; safe to import from client components. */

/** Why a line is or is not on a factura (`authorization_line.match_status`). */
export const AUTH_STATUS_LABELS: Record<string, string> = {
  linked: "Vinculada por el emparejador",
  review: "En revisión",
  low_score: "Puntaje bajo",
  no_candidate: "Sin factura en la aseguradora",
  no_person: "Sin persona",
  duplicate: "Duplicada",
  staff: "Decidida por el equipo",
};

export const AUTH_STATUS_HINTS: Record<string, string> = {
  linked: "El emparejador encontró una sola factura con puntaje suficiente.",
  review: "Hay una factura probable; una persona debe confirmarla en Revisión.",
  low_score: "La persona o el titular tienen facturas en la aseguradora, pero ninguna coincide lo suficiente.",
  no_candidate: "Ni la persona ni el titular tienen facturas cargadas en esa aseguradora.",
  no_person: "La línea no identifica paciente, titular ni clave.",
  duplicate: "Es copia de otra solicitud y no cuenta en los totales.",
  staff: "Una persona la vinculó o desvinculó en Autorizaciones; el emparejador no la cambia.",
};

/** `?estado=` values on the list: link state first, then the stored reason. */
export const AUTH_ESTADO_LABELS: Record<string, string> = {
  vinculada: "Con factura",
  pendiente: "Sin factura",
  revision: "Revisión abierta",
  low_score: "Puntaje bajo",
  no_candidate: "Sin factura en la aseguradora",
  no_person: "Sin persona",
  staff: "Decidida por el equipo",
};

export const AUTH_FECHA_LABELS: Record<string, string> = {
  exacta: "Fecha exacta",
  periodo: "Solo el mes",
  sin: "Sin fecha",
};

export const AUTH_DATE_SOURCE_LABELS: Record<string, string> = {
  request: "Fecha de solicitud",
  service: "Fecha de servicio",
  period: "Mes del archivo",
  period_day: "Día del archivo",
  sin: "Sin fecha",
};

export const AUTH_SIGNAL_LABELS: Record<string, string> = {
  clave: "Clave igual",
  person: "Paciente en la factura",
  titular: "Titular en la factura",
  amount: "Monto parecido",
  service: "Servicio parecido",
  only_candidate: "Única factura posible",
  "date:stale": "Factura muy posterior",
  "date:after_issue": "Factura anterior a la autorización",
  "period:0m": "Factura del mismo mes",
  "period:1m": "Factura del mes siguiente",
  "period:after_issue": "Factura anterior al mes",
  "period:stale": "Factura muy posterior al mes",
};

export const AUTH_LAG_BUCKETS: { key: string; label: string }[] = [
  { key: "antes", label: "Factura antes de la autorización" },
  { key: "0-7", label: "0 a 7 días" },
  { key: "8-15", label: "8 a 15 días" },
  { key: "16-30", label: "16 a 30 días" },
  { key: "31-60", label: "31 a 60 días" },
  { key: "61+", label: "Más de 60 días" },
];

/** `field_provenance.rule_id` written for authorization lines, items, and sources. */
export const AUTH_RULE_LABELS: Record<string, string> = {
  authorization_item: "Ítem del libro",
  authorization_source: "Fila del libro",
  authorization_date_repair: "Reparación de fechas",
  authorization_fields: "Aseguradora y proveedor",
  authorization_titular: "Titular del libro",
  authorization_aps_code: "Código APS",
  authorization_service_label: "Servicio del libro",
  authorization_duplicate: "Línea duplicada",
  duplicate_workbook_row: "Fila repetida en el libro",
  match_auth_lines: "Emparejador de facturas",
  review_auth_match: "Revisión aceptada",
  staff_link_authorization: "Vinculada por el equipo",
  staff_unlink_authorization: "Desvinculada por el equipo",
  especialidad_auth_exact: "Especialidad por nombre exacto",
  especialidad_auth_phrase: "Especialidad por frase",
  especialidad_auth_fuzzy: "Especialidad aproximada",
  especialidad_auth_suffix_fragment: "Especialidad por sufijo",
  near_ci_auth_remount: "Cédula casi igual",
  stored_string_not_a_person: "Texto que no es una persona",
  form_legend_not_a_person: "Leyenda del formulario",
};

export const SOURCE_KIND_LABELS: Record<string, string> = {
  workbook: "Libro de la aseguradora",
  ocr: "Lectura del documento",
  path: "Ruta del archivo",
  case_evidence: "Expediente",
  manual: "Equipo",
  review: "Revisión",
  derived: "Derivado",
};

export const AUTH_VIA_LABELS: Record<string, string> = {
  person: "Factura del paciente",
  titular: "Factura del titular",
  clave: "Misma clave",
  review: "Sugerida en revisión",
};

export function authSignalLabel(signal: string): string {
  if (AUTH_SIGNAL_LABELS[signal]) return AUTH_SIGNAL_LABELS[signal];
  const days = /^date:(\d+)d$/.exec(signal);
  if (days) return `Factura ${days[1]} días después`;
  return signal;
}

const AUTH_REASON_LABELS: Record<string, string> = {
  "period:named": "Mes tomado del nombre de la hoja o del archivo",
  "period:saved": "Mes tomado de la fecha en que se guardó el libro",
  service_label: "Servicio leído de la fila",
  workbook_row: "Fila de origen registrada",
};

/** `field_provenance.reason` in words: known reasons, cleared placeholders, or the matcher's signals. */
export function authReasonLabel(reason: string): string {
  if (AUTH_REASON_LABELS[reason]) return AUTH_REASON_LABELS[reason];
  const cleared = /^cleared:(\w+)$/.exec(reason);
  if (cleared) return `Se borró la fecha vacía de Excel (${cleared[1]})`;
  const parts = reason.split("+");
  const labels = parts.map(authSignalLabel);
  if (labels.every((label, i) => label !== parts[i])) return labels.join(", ");
  return reason;
}

/** Status shown on a line, reading the link and the stored reason together. */
export function authStatusLabel(status: string | null, invoiceId: string | null): string {
  if (status === "review" && invoiceId) return "Vinculada en revisión";
  if (status === "staff") return invoiceId ? "Vinculada por el equipo" : "Desvinculada por el equipo";
  if (!status) return invoiceId ? "Vinculada" : "Sin evaluar";
  return AUTH_STATUS_LABELS[status] ?? status;
}
