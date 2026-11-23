import type { AuthorizationListFilters } from "@/lib/authorization-data";
import { AUTH_ESTADO_LABELS, AUTH_FECHA_LABELS } from "@/lib/authorization-labels";
import { firstParam, normalizeQuery } from "@/lib/list-params";

/** URL params for /autorizaciones and /api/v1/autorizaciones. */
export type AutorizacionesSearchInput = {
  q?: string;
  aseguradora?: string;
  contratante?: string;
  estado?: string;
  fecha?: string;
  especialidad?: string;
  anio?: string;
  desde?: string;
  hasta?: string;
  vista?: string;
  rango?: string;
  page?: string;
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isoDate(raw: string | undefined): string {
  const v = firstParam(raw);
  return ISO_DATE.test(v) && !Number.isNaN(Date.parse(v)) ? v : "";
}

function oneOf(raw: string | undefined, allowed: Record<string, string>): string {
  const v = firstParam(raw);
  return v in allowed ? v : "";
}

/** Filter params that the list, the chips, and pagination share. `vista` and `rango` are carried separately. */
export function autorizacionFilterParams(sp: AutorizacionesSearchInput): Record<string, string | undefined> {
  const anio = firstParam(sp.anio);
  return {
    q: normalizeQuery(sp.q) || undefined,
    aseguradora: firstParam(sp.aseguradora) || undefined,
    contratante: firstParam(sp.contratante) || undefined,
    estado: oneOf(sp.estado, AUTH_ESTADO_LABELS) || undefined,
    fecha: oneOf(sp.fecha, AUTH_FECHA_LABELS) || undefined,
    especialidad: firstParam(sp.especialidad) || undefined,
    anio: /^\d{4}$/.test(anio) ? anio : undefined,
    desde: isoDate(sp.desde) || undefined,
    hasta: isoDate(sp.hasta) || undefined,
  };
}

/** Data-layer filters from parsed params. The year narrows the range; explicit desde/hasta win. */
export function authorizationListFilters(
  params: Record<string, string | undefined>,
  pageSize: number,
  requestedPage: number,
): AuthorizationListFilters {
  const query = params.q || "";
  return {
    query,
    like: `%${query}%`,
    aseguradora: params.aseguradora || "",
    contratante: params.contratante || "",
    estado: params.estado || "",
    fecha: params.fecha || "",
    especialidad: params.especialidad || "",
    desde: params.desde || (params.anio ? `${params.anio}-01-01` : ""),
    hasta: params.hasta || (params.anio ? `${params.anio}-12-31` : ""),
    pageSize,
    requestedPage,
  };
}
