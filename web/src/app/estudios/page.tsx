import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { EmptyState } from "@/components/empty-state";
import { EntityRow } from "@/components/entity-row";
import { EntityTabs, type EntityTabPanel } from "@/components/entity-tabs";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ESTUDIO_FAMILIES,
  getEstudioSummary,
  isEstudioDetail,
  isEstudioProcedure,
  queryEstudioCatalog,
  queryEstudioList,
  type EstudioProcedureTile,
  type EstudioSummary,
} from "@/lib/estudio-data";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { buildListHref, firstParam, hasActiveFilters, normalizeQuery, omitParam, type ActiveChip } from "@/lib/list-params";

export const metadata: Metadata = {
  title: "Estudios · Ávila GPS",
  description: "Pruebas diagnósticas por familia. Cada estudio abre las facturas y las personas que lo tienen.",
};

export const dynamic = "force-dynamic";

const n = (value: number) => value.toLocaleString("es-VE");

function countLabel(count: number, one: string, many: string): string {
  return `${n(count)} ${count === 1 ? one : many}`;
}

function familyOf(procedure: string) {
  return ESTUDIO_FAMILIES.find((family) => family.id === procedure || family.codes.includes(procedure));
}

function ProcedureGrid({ items }: { items: EstudioProcedureTile[] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <li key={`${item.code}:${item.name}`} className="rounded-2xl border border-border bg-muted/60 p-4">
          <Link href={`/estudios?detalle=${encodeURIComponent(item.name)}`} className="font-medium text-brand hover:underline">
            {item.name}
          </Link>
          <p className="mt-1 text-xs tabular-nums text-muted-foreground">
            {countLabel(item.facturas, "factura", "facturas")} · {countLabel(item.withResult, "con resultado", "con resultado")}
          </p>
        </li>
      ))}
    </ul>
  );
}

function OpenListCard({ href, title, detail }: { href: string; title: string; detail: string }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <li className="rounded-2xl border border-border bg-muted/60 p-4">
        <Link href={href} className="font-medium text-brand hover:underline">
          {title}
        </Link>
        <p className="mt-1 text-xs tabular-nums text-muted-foreground">{detail}</p>
      </li>
    </ul>
  );
}

function TabsFallback() {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6" aria-hidden="true">
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 7 }, (_, index) => (
          <Skeleton key={index} className="h-9 w-36 rounded-full" />
        ))}
      </div>
      <Skeleton className="mt-5 h-6 w-48 rounded-lg" />
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-28 rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

function EstudioTabs({
  summary,
  catalog,
  requested,
}: {
  summary: EstudioSummary;
  catalog: EstudioProcedureTile[];
  requested: string;
}) {
  const panels: EntityTabPanel[] = ESTUDIO_FAMILIES.flatMap((family) => {
    const facturas = summary.families.find((item) => item.id === family.id)?.n ?? 0;
    if (facturas === 0) return [];
    if (family.codes.length === 0) {
      return [
        {
          id: family.id,
          label: family.label,
          count: n(facturas),
          title: family.label,
          description: countLabel(facturas, "factura", "facturas"),
          body: (
            <OpenListCard
              href={`/estudios?procedimiento=${family.id}`}
              title={family.label}
              detail="Abre las facturas y las personas de este grupo."
            />
          ),
        },
      ];
    }
    const items = catalog.filter((item) => item.familyId === family.id);
    return [
      {
        id: family.id,
        label: family.label,
        count: n(items.length),
        title: family.label,
        description: `${countLabel(items.length, "estudio", "estudios")} · ${countLabel(facturas, "factura", "facturas")}`,
        body: <ProcedureGrid items={items} />,
      },
    ];
  });
  const defaultFamily = panels.some((panel) => panel.id === requested) ? requested : (panels[0]?.id ?? "laboratorio");
  if (panels.length === 0) {
    return <EmptyState title="Aún no hay estudios" hint="El extractor todavía no escribió pruebas diagnósticas." />;
  }
  return (
    <Suspense fallback={<TabsFallback />}>
      <EntityTabs panels={panels} defaultValue={defaultFamily} paramName="familia" ariaLabel="Familias de estudio" />
    </Suspense>
  );
}

export default async function EstudiosPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; familia?: string; procedimiento?: string; detalle?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const procedureRaw = firstParam(sp.procedimiento);
  const procedure = isEstudioProcedure(procedureRaw) ? procedureRaw : "";
  const detailRaw = firstParam(sp.detalle);
  const detail = isEstudioDetail(detailRaw) ? detailRaw.trim() : "";
  const summary = await getEstudioSummary();

  if (!procedure && !detail) {
    const catalog = await queryEstudioCatalog();
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Clínica"
          title="Estudios"
          description="Familia y el estudio más específico que se pudo leer. La consulta queda fuera."
          badges={[{ label: countLabel(summary.facturas, "factura", "facturas") }]}
        />
        <div className="flex justify-end">
          <Link href="/estudios/catalogo" className="rounded-full border border-border px-4 py-2 text-sm font-medium text-brand">
            Catálogo de la clínica
          </Link>
        </div>
        <EstudioTabs summary={summary} catalog={catalog} requested={firstParam(sp.familia)} />
      </div>
    );
  }

  const query = normalizeQuery(sp.q);
  const list = await queryEstudioList({
    query,
    family: "",
    procedure: detail ? "" : procedure,
    detail,
    page: parsePage(firstParam(sp.page) || undefined),
  });
  const catalog = await queryEstudioCatalog();
  const named = catalog.find((item) => (detail ? item.name === detail : item.code === procedure));
  const family = familyOf(detail ? named?.code || "" : procedure);
  const title = detail || named?.name || family?.label || "Estudios";
  const params = { q: query, procedimiento: detail ? "" : procedure, detalle: detail };
  const chips: ActiveChip[] = [];
  if (query) {
    chips.push({
      key: "q",
      label: `Buscar: ${query}`,
      clearHref: buildListHref("/estudios", omitParam(params, "q")),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Clínica"
        title={title}
        description="Facturas y personas con este estudio. La consulta no entra."
        badges={[{ label: countLabel(list.total, "factura", "facturas") }]}
      />
      <div className="flex justify-end">
        <Link
          href={family ? `/estudios?familia=${family.id}` : "/estudios"}
          className="rounded-full border border-border px-4 py-2 text-sm font-medium text-brand"
        >
          Volver a {family?.label || "Estudios"}
        </Link>
      </div>
      <ListFilterBar
        searchValue={firstParam(sp.q)}
        searchPlaceholder="Factura o paciente (mín. 2)"
        searchLabel="Buscar"
        clearHref={hasActiveFilters(params) ? (detail ? `/estudios?detalle=${encodeURIComponent(detail)}` : `/estudios?procedimiento=${procedure}`) : undefined}
        carry={{ procedimiento: detail ? "" : procedure, detalle: detail }}
        activeChips={chips}
      />
      <ResultCount shown={list.rows.length} total={list.total} page={list.page} pageSize={DEFAULT_PAGE_SIZE} />
      {list.rows.length === 0 ? (
        <EmptyState title="No se encontraron estudios" hint="Prueba otro término o quita la búsqueda." />
      ) : (
        <div className="space-y-2">
          {list.rows.map((row) => (
            <EntityRow
              key={row.id}
              href={`/facturas/${row.id}`}
              title={formatInvoiceNumber(row.invoiceNumber)}
              badges={[
                row.charged ? "Con cargo" : null,
                row.hasResult ? "Con resultado" : null,
                row.charged && !row.hasResult ? "Sin resultado" : null,
              ].filter((badge): badge is string => Boolean(badge))}
              meta={[row.patientName, row.issueDate ? formatDate(row.issueDate) : null, row.labels.join(" · ")]
                .filter(Boolean)
                .join(" · ")}
            />
          ))}
        </div>
      )}
      <Pagination
        page={list.page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={list.total}
        shown={list.rows.length}
        basePath="/estudios"
        searchParams={params}
      />
    </div>
  );
}
