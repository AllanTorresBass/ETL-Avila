import {
  BadgeCheck,
  FileWarning,
  IdCard,
  Link2,
  Phone,
  ReceiptText,
  UserRound,
  Users,
} from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import type { PersonaListKpis } from "@/lib/persona-data";

const n = (v: number) => v.toLocaleString("es-VE");

export type PersonaListFilterState = {
  has_ci?: string;
  has_phone?: string;
  has_invoice?: string;
  role?: string;
  has_contact_gap?: string;
  incomplete_name?: string;
};

function isActive(
  filters: PersonaListFilterState,
  match: PersonaListFilterState,
): boolean {
  const keys = Object.keys(match) as (keyof PersonaListFilterState)[];
  if (keys.length === 0) {
    return (
      !filters.has_ci &&
      !filters.has_phone &&
      !filters.has_invoice &&
      !filters.role &&
      !filters.has_contact_gap &&
      !filters.incomplete_name
    );
  }
  return keys.every((key) => filters[key] === match[key]);
}

/** Clickable corpus KPIs — each card applies (or clears) a Personas list filter via URL. */
export function PersonaListKpisStrip({
  kpis,
  filters = {},
}: {
  kpis: PersonaListKpis;
  filters?: PersonaListFilterState;
}) {
  return (
    <section aria-label="Indicadores del archivo" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        featured
        label="Personas"
        value={n(kpis.total)}
        hint={`${n(kpis.withIdentityDocs)} con documentos de identidad · quita filtros`}
        href="/personas#lista"
        active={isActive(filters, {})}
        icon={<Users className="size-4" />}
      />
      <KpiCard
        label="Con cédula"
        value={n(kpis.withCi)}
        hint={`${n(kpis.withoutCi)} sin cédula`}
        href="/personas?has_ci=1#lista"
        active={isActive(filters, { has_ci: "1" })}
        icon={<IdCard className="size-4" />}
      />
      <KpiCard
        label="Sin cédula"
        value={n(kpis.withoutCi)}
        hint="Prioridad de enriquecimiento"
        href="/personas?has_ci=0#lista"
        active={isActive(filters, { has_ci: "0" })}
        icon={<FileWarning className="size-4" />}
      />
      <KpiCard
        label="Con factura"
        value={n(kpis.withInvoice)}
        hint={`${n(kpis.withoutInvoice)} sin factura`}
        href="/personas?has_invoice=1#lista"
        active={isActive(filters, { has_invoice: "1" })}
        icon={<ReceiptText className="size-4" />}
      />
      <KpiCard
        label="Sin factura"
        value={n(kpis.withoutInvoice)}
        hint="Huérfanos del archivo"
        href="/personas?has_invoice=0#lista"
        active={isActive(filters, { has_invoice: "0" })}
        icon={<Link2 className="size-4" />}
      />
      <KpiCard
        label="Titulares"
        value={n(kpis.titulares)}
        hint={`${n(kpis.beneficiarios)} beneficiarios`}
        href="/personas?role=titular#lista"
        active={isActive(filters, { role: "titular" })}
        icon={<BadgeCheck className="size-4" />}
      />
      <KpiCard
        label="Beneficiarios"
        value={n(kpis.beneficiarios)}
        href="/personas?role=beneficiario#lista"
        active={isActive(filters, { role: "beneficiario" })}
        icon={<UserRound className="size-4" />}
      />
      <KpiCard
        label="Con teléfono"
        value={n(kpis.withPhone)}
        hint={`${n(kpis.withoutPhone)} sin teléfono`}
        href="/personas?has_phone=1#lista"
        active={isActive(filters, { has_phone: "1" })}
        icon={<Phone className="size-4" />}
      />
    </section>
  );
}
