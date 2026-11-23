import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { EmptyState } from "@/components/empty-state";
import { EntityTabs, type EntityTabPanel } from "@/components/entity-tabs";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { requirePermission } from "@/lib/auth";
import { queryClinicCatalog, type ClinicStudy } from "@/lib/estudio-data";
import { firstParam } from "@/lib/list-params";

export const metadata: Metadata = {
  title: "Catálogo de estudios · Ávila GPS",
  description: "Estudios que maneja la clínica, con su familia y su especificación.",
};

export const dynamic = "force-dynamic";

const n = (value: number) => value.toLocaleString("es-VE");

function countLabel(count: number, one: string, many: string): string {
  return `${n(count)} ${count === 1 ? one : many}`;
}

function StudyCard({ study }: { study: ClinicStudy }) {
  return (
    <article className="rounded-2xl border border-border bg-muted/60 p-4">
      <h3 className="font-medium text-foreground">{study.name}</h3>
      <p className="mt-1 text-xs tabular-nums text-muted-foreground">{countLabel(study.estudios, "estudio", "estudios")}</p>
      {study.specs.length > 0 ? (
        <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
          {study.unspecified > 0 ? (
            <li className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-muted-foreground">Sin especificación</span>
              <span className="tabular-nums text-muted-foreground">{n(study.unspecified)}</span>
            </li>
          ) : null}
          {study.specs.map((spec) => (
            <li key={spec.code} className="flex items-baseline justify-between gap-3 text-sm">
              <span>{spec.name}</span>
              <span className="tabular-nums text-muted-foreground">{n(spec.estudios)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function TabsFallback() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6" aria-hidden="true">
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-9 w-32 rounded-full" />
        ))}
      </div>
      <Skeleton className="mt-5 h-40 rounded-2xl" />
    </div>
  );
}

export default async function EstudioCatalogoPage({
  searchParams,
}: {
  searchParams: Promise<{ familia?: string }>;
}) {
  await requirePermission("read");
  const sp = await searchParams;
  const catalog = await queryClinicCatalog();
  const panels: EntityTabPanel[] = catalog.families.map((family) => ({
    id: family.code,
    label: family.name,
    count: n(family.studies.length),
    title: family.name,
    description: `${countLabel(family.studies.length, "estudio", "estudios")} · ${countLabel(family.estudios, "registro", "registros")}`,
    body: (
      <ul className="grid gap-3 sm:grid-cols-2">
        {family.studies.map((study) => (
          <li key={study.code}>
            <StudyCard study={study} />
          </li>
        ))}
      </ul>
    ),
  }));
  const requested = firstParam(sp.familia);
  const defaultFamily = panels.some((panel) => panel.id === requested) ? requested : (panels[0]?.id ?? "laboratorio");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Clínica"
        title="Catálogo"
        description="El estudio es el servicio que maneja la clínica. La especificación es el examen cuando el documento lo nombra, como Hematología completa dentro de Exámenes de laboratorio."
        badges={[{ label: countLabel(catalog.studies, "estudio", "estudios") }]}
      />
      <div className="flex justify-end">
        <Link href="/estudios" className="rounded-full border border-border px-4 py-2 text-sm font-medium text-brand">
          Volver a Estudios
        </Link>
      </div>
      {panels.length === 0 ? (
        <EmptyState title="Aún no hay catálogo" hint="El normalizador todavía no escribió los tipos de la clínica." />
      ) : (
        <Suspense fallback={<TabsFallback />}>
          <EntityTabs panels={panels} defaultValue={defaultFamily} paramName="familia" ariaLabel="Familias de estudio" />
        </Suspense>
      )}
      {catalog.withoutType > 0 ? (
        <p className="text-sm text-muted-foreground">
          {countLabel(catalog.withoutType, "registro", "registros")} sin tipo de la clínica. La página solo decía Estudio o Imagenología.
        </p>
      ) : null}
    </div>
  );
}
