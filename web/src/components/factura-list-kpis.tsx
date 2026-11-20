import {
  BadgeCheck,
  FileText,
  FileWarning,
  Link2,
  ReceiptText,
  UserRound,
  Users,
} from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import type { FacturaListKpis } from "@/lib/factura-data";

const n = (v: number) => v.toLocaleString("es-VE");

export type FacturaListFilterState = {
  has_person?: string;
  has_titular?: string;
  has_docs?: string;
};

function isActive(
  filters: FacturaListFilterState,
  match: FacturaListFilterState,
): boolean {
  const keys = Object.keys(match) as (keyof FacturaListFilterState)[];
  if (keys.length === 0) {
    return !filters.has_person && !filters.has_titular && !filters.has_docs;
  }
  return keys.every((key) => filters[key] === match[key]);
}

/** Clickable corpus KPIs — each card applies (or clears) a Facturas list filter via URL. */
export function FacturaListKpisStrip({
  kpis,
  filters = {},
}: {
  kpis: FacturaListKpis;
  filters?: FacturaListFilterState;
}) {
  return (
    <section aria-label="Indicadores de facturas" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        featured
        label="Facturas"
        value={n(kpis.total)}
        hint="Quita filtros del listado"
        href="/facturas#lista"
        active={isActive(filters, {})}
        icon={<ReceiptText className="size-4" />}
      />
      <KpiCard
        label="Con persona"
        value={n(kpis.withPerson)}
        hint={`${n(kpis.withoutPerson)} sin persona`}
        href="/facturas?has_person=1#lista"
        active={isActive(filters, { has_person: "1" })}
        icon={<Users className="size-4" />}
      />
      <KpiCard
        label="Sin persona"
        value={n(kpis.withoutPerson)}
        hint="Huérfanas del archivo"
        href="/facturas?has_person=0#lista"
        active={isActive(filters, { has_person: "0" })}
        icon={<Link2 className="size-4" />}
      />
      <KpiCard
        label="Con titular"
        value={n(kpis.withTitular)}
        hint={`${n(kpis.withoutTitular)} sin titular`}
        href="/facturas?has_titular=1#lista"
        active={isActive(filters, { has_titular: "1" })}
        icon={<BadgeCheck className="size-4" />}
      />
      <KpiCard
        label="Sin titular"
        value={n(kpis.withoutTitular)}
        hint="Prioridad de roles"
        href="/facturas?has_titular=0#lista"
        active={isActive(filters, { has_titular: "0" })}
        icon={<UserRound className="size-4" />}
      />
      <KpiCard
        label="Con documentos"
        value={n(kpis.withDocs)}
        hint={`${n(kpis.withoutDocs)} sin páginas`}
        href="/facturas?has_docs=1#lista"
        active={isActive(filters, { has_docs: "1" })}
        icon={<FileText className="size-4" />}
      />
      <KpiCard
        label="Sin documentos"
        value={n(kpis.withoutDocs)}
        hint="Falta carga de páginas"
        href="/facturas?has_docs=0#lista"
        active={isActive(filters, { has_docs: "0" })}
        icon={<FileWarning className="size-4" />}
      />
      <KpiCard
        label="Revisión abierta"
        value={n(kpis.openInvoiceReviews)}
        hint="Casos con factura vinculada"
        href="/revision"
        icon={<BadgeCheck className="size-4" />}
      />
    </section>
  );
}
