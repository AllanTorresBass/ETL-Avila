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

/** Clickable corpus KPIs that jump into common Personas filters. */
export function PersonaListKpisStrip({ kpis }: { kpis: PersonaListKpis }) {
  return (
    <section aria-label="Indicadores del archivo" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        featured
        label="Personas"
        value={n(kpis.total)}
        hint={`${n(kpis.withIdentityDocs)} con docs de identidad`}
        href="/personas"
        icon={<Users className="size-4" />}
      />
      <KpiCard
        label="Con cédula"
        value={n(kpis.withCi)}
        hint={`${n(kpis.withoutCi)} sin cédula`}
        href="/personas?has_ci=1"
        icon={<IdCard className="size-4" />}
      />
      <KpiCard
        label="Sin cédula"
        value={n(kpis.withoutCi)}
        hint="Prioridad de enriquecimiento"
        href="/personas?has_ci=0"
        icon={<FileWarning className="size-4" />}
      />
      <KpiCard
        label="Con factura"
        value={n(kpis.withInvoice)}
        hint={`${n(kpis.withoutInvoice)} sin factura`}
        href="/personas?has_invoice=1"
        icon={<ReceiptText className="size-4" />}
      />
      <KpiCard
        label="Sin factura"
        value={n(kpis.withoutInvoice)}
        hint="Huérfanos del archivo"
        href="/personas?has_invoice=0"
        icon={<Link2 className="size-4" />}
      />
      <KpiCard
        label="Titulares"
        value={n(kpis.titulares)}
        hint={`${n(kpis.beneficiarios)} beneficiarios`}
        href="/personas?role=titular"
        icon={<BadgeCheck className="size-4" />}
      />
      <KpiCard
        label="Beneficiarios"
        value={n(kpis.beneficiarios)}
        href="/personas?role=beneficiario"
        icon={<UserRound className="size-4" />}
      />
      <KpiCard
        label="Con teléfono"
        value={n(kpis.withPhone)}
        hint={`${n(kpis.withoutPhone)} sin teléfono`}
        href="/personas?has_phone=1"
        icon={<Phone className="size-4" />}
      />
      <KpiCard
        label="Gaps de contacto"
        value={n(kpis.withContactGaps)}
        hint={`${n(kpis.incompleteName)} nombre incompleto`}
        icon={<FileWarning className="size-4" />}
      />
      <KpiCard
        label="Revisión abierta"
        value={n(kpis.openPersonReviews)}
        hint="Casos con persona vinculada"
        href="/revision"
        icon={<BadgeCheck className="size-4" />}
      />
    </section>
  );
}
