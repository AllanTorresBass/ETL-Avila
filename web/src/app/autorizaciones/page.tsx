import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { FileCheck } from "lucide-react";
import { AuthorizationAnalyticsView } from "@/components/authorization-analytics";
import {
  AutorizacionesAnalyticsSkeleton,
  AutorizacionesListSkeleton,
} from "@/components/autorizaciones-page-skeleton";
import { AutorizacionesResults } from "@/components/autorizaciones-results";
import { KpiCard } from "@/components/kpi-card";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { ScrollToAnchor } from "@/components/scroll-to-anchor";
import { getAuthorizationKpis, listAuthorizationFilterOptions } from "@/lib/authorization-data";
import { autorizacionFilterParams, type AutorizacionesSearchInput } from "@/lib/authorization-filters";
import { AUTH_ESTADO_LABELS, AUTH_FECHA_LABELS } from "@/lib/authorization-labels";
import { BI_RANGES, parseRange } from "@/lib/dashboard-data";
import { formatPercent, formatUsdCompact } from "@/lib/format-metrics";
import { buildListHref, firstParam, hasActiveFilters, omitParam, type ActiveChip } from "@/lib/list-params";

export const metadata: Metadata = {
  title: "Autorizaciones · Ávila GPS",
  description: "Autorizaciones de las aseguradoras: de qué libro vienen, a quién cubren, qué factura las cobra y por qué.",
};

export const dynamic = "force-dynamic";

const n = (v: number) => v.toLocaleString("es-VE");

type Vista = "lista" | "analisis";

function ViewTabs({ vista, params }: { vista: Vista; params: Record<string, string | undefined> }) {
  const tabs: { id: Vista; label: string }[] = [
    { id: "lista", label: "Lista" },
    { id: "analisis", label: "Análisis" },
  ];
  return (
    <nav aria-label="Vista" className="inline-flex gap-1 rounded-full border border-border bg-card p-1 shadow-sm">
      {tabs.map((t) => (
        <Link
          key={t.id}
          href={buildListHref("/autorizaciones", { ...params, vista: t.id === "lista" ? undefined : t.id })}
          aria-current={vista === t.id ? "page" : undefined}
          scroll={false}
          className={`inline-flex min-h-9 items-center rounded-full px-4 text-sm font-medium transition-colors ${
            vista === t.id ? "bg-brand text-primary-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

function RangeTabs({ current }: { current: string }) {
  return (
    <nav aria-label="Periodo" className="inline-flex gap-1 rounded-full border border-border bg-card p-1 shadow-sm">
      {BI_RANGES.map((r) => (
        <Link
          key={r.id}
          href={`/autorizaciones?vista=analisis&rango=${r.id}`}
          aria-current={r.id === current ? "true" : undefined}
          scroll={false}
          className={`inline-flex min-h-9 items-center rounded-full px-3 text-sm font-medium transition-colors ${
            r.id === current ? "bg-brand text-primary-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {r.label}
        </Link>
      ))}
    </nav>
  );
}

export default async function AutorizacionesPage({ searchParams }: { searchParams: Promise<AutorizacionesSearchInput> }) {
  const sp = await searchParams;
  const vista: Vista = firstParam(sp.vista) === "analisis" ? "analisis" : "lista";
  const [kpis, options] = await Promise.all([getAuthorizationKpis(), listAuthorizationFilterOptions()]);
  const params = autorizacionFilterParams(sp);
  const linkedShare = kpis.lines > 0 ? kpis.linked / kpis.lines : 0;

  const label = {
    aseguradora: new Map(options.aseguradoras.map((o) => [o.value, o.label])),
    especialidad: new Map(options.especialidades.map((o) => [o.value, o.label])),
  };
  const chips: ActiveChip[] = [];
  const chip = (key: string, text: string) =>
    chips.push({ key, label: text, clearHref: `${buildListHref("/autorizaciones", omitParam(params, key))}#lista` });
  if (params.q) chip("q", `Buscar: ${params.q}`);
  if (params.aseguradora) chip("aseguradora", label.aseguradora.get(params.aseguradora) || params.aseguradora);
  if (params.contratante) chip("contratante", params.contratante);
  if (params.estado) chip("estado", AUTH_ESTADO_LABELS[params.estado]);
  if (params.fecha) chip("fecha", AUTH_FECHA_LABELS[params.fecha]);
  if (params.especialidad) chip("especialidad", label.especialidad.get(params.especialidad) || params.especialidad);
  if (params.anio) chip("anio", `Año ${params.anio}`);
  if (params.desde) chip("desde", `Desde ${params.desde}`);
  if (params.hasta) chip("hasta", `Hasta ${params.hasta}`);

  const listKey = JSON.stringify({ ...params, page: firstParam(sp.page) || "1" });
  const range = firstParam(sp.rango) ? parseRange(sp.rango) : "todo";
  const months = BI_RANGES.find((r) => r.id === range)?.months ?? 0;

  return (
    <div className="space-y-6">
      <Suspense fallback={null}>
        <ScrollToAnchor id="lista" />
      </Suspense>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageHeader
          eyebrow="Registros"
          title="Autorizaciones"
          description="Cada línea sale de un libro de la aseguradora. Aquí se ve a quién cubre, qué factura la cobra y, si no tiene, por qué."
        />
        <ViewTabs vista={vista} params={vista === "lista" ? params : {}} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          featured
          label="Autorizaciones"
          value={n(kpis.lines)}
          hint={`${formatPercent(linkedShare)} con factura`}
          icon={<FileCheck className="size-4" />}
        />
        <KpiCard
          label="Con factura"
          value={n(kpis.linked)}
          hint={kpis.requestedUsd > 0 ? `${formatUsdCompact(kpis.requestedUsd)} solicitados en total` : undefined}
          href="/autorizaciones?estado=vinculada#lista"
          active={params.estado === "vinculada"}
        />
        <KpiCard
          label="Sin factura, con candidatas"
          value={n(kpis.actionable)}
          hint={`${n(kpis.inReview)} en revisión`}
          href="/autorizaciones?estado=revision#lista"
          active={params.estado === "revision"}
        />
        <KpiCard
          label="Sin fecha exacta"
          value={n(kpis.noExactDate)}
          hint={`${n(kpis.noDate)} sin mes conocido`}
          href="/autorizaciones?fecha=periodo#lista"
          active={params.fecha === "periodo"}
        />
      </div>

      {vista === "analisis" ? (
        <div className="space-y-4">
          <RangeTabs current={range} />
          <Suspense key={range} fallback={<AutorizacionesAnalyticsSkeleton />}>
            <AuthorizationAnalyticsView months={months} />
          </Suspense>
        </div>
      ) : (
        <>
          <ListFilterBar
            searchValue={firstParam(sp.q)}
            searchPlaceholder="Clave, APS, cédula, nombre o diagnóstico (mín. 2)"
            searchLabel="Buscar"
            clearHref={hasActiveFilters(params) ? "/autorizaciones#lista" : undefined}
            hash="lista"
            activeChips={chips}
            carry={{ desde: params.desde || "", hasta: params.hasta || "" }}
            selects={[
              {
                name: "estado",
                label: "Estado",
                value: params.estado || "",
                emptyLabel: "Todos",
                options: Object.entries(AUTH_ESTADO_LABELS).map(([value, text]) => ({ value, label: text })),
              },
              {
                name: "aseguradora",
                label: "Aseguradora",
                value: params.aseguradora || "",
                emptyLabel: "Todas",
                options: options.aseguradoras,
              },
              {
                name: "contratante",
                label: "Contratante",
                value: params.contratante || "",
                emptyLabel: "Todos",
                options: options.contratantes,
              },
              {
                name: "especialidad",
                label: "Especialidad",
                value: params.especialidad || "",
                emptyLabel: "Todas",
                options: options.especialidades,
              },
              {
                name: "fecha",
                label: "Fecha",
                value: params.fecha || "",
                emptyLabel: "Todas",
                options: Object.entries(AUTH_FECHA_LABELS).map(([value, text]) => ({ value, label: text })),
              },
              {
                name: "anio",
                label: "Año",
                value: params.anio || "",
                emptyLabel: "Todos",
                options: options.years.map((y) => ({ value: y, label: y })),
              },
            ]}
          />
          <Suspense key={listKey} fallback={<AutorizacionesListSkeleton />}>
            <AutorizacionesResults sp={sp} />
          </Suspense>
        </>
      )}
    </div>
  );
}
