import type { Metadata } from "next";
import { FlaskConical } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { EntityRow } from "@/components/entity-row";
import { KpiCard } from "@/components/kpi-card";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import {
  ESTUDIO_FAMILIES,
  getEstudioSummary,
  isEstudioFamily,
  queryEstudioList,
} from "@/lib/estudio-data";
import { formatDate, formatInvoiceNumber } from "@/lib/format";
import { buildListHref, firstParam, hasActiveFilters, normalizeQuery, omitParam, type ActiveChip } from "@/lib/list-params";

export const metadata: Metadata = {
  title: "Estudios · Ávila GPS",
  description: "Pruebas diagnósticas leídas de la factura, la hoja de resultado y la orden de estudio.",
};

export const dynamic = "force-dynamic";

const n = (value: number) => value.toLocaleString("es-VE");

export default async function EstudiosPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; familia?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const query = normalizeQuery(sp.q);
  const familyRaw = firstParam(sp.familia);
  const family = isEstudioFamily(familyRaw) ? familyRaw : "";
  const [summary, list] = await Promise.all([
    getEstudioSummary(),
    queryEstudioList({ query, family, page: parsePage(firstParam(sp.page) || undefined) }),
  ]);
  const params = { q: query, familia: family };
  const chips: ActiveChip[] = [];
  if (query) {
    chips.push({
      key: "q",
      label: `Buscar: ${query}`,
      clearHref: buildListHref("/estudios", omitParam(params, "q")),
    });
  }
  const familyLabel = ESTUDIO_FAMILIES.find((item) => item.id === family)?.label;
  if (family && familyLabel) {
    chips.push({
      key: "familia",
      label: familyLabel,
      clearHref: buildListHref("/estudios", omitParam(params, "familia")),
    });
  }
  const baseWithoutFamily = omitParam(params, "familia");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Clínica"
        title="Estudios"
        description="Laboratorio, imagen y otras pruebas. La consulta queda fuera. El cargo, la hoja de resultado y la orden se leen por separado."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard featured label="Facturas con un estudio" value={n(summary.facturas)} icon={<FlaskConical className="size-4" />} />
        <KpiCard label="Con cargo del estudio" value={n(summary.charged)} />
        <KpiCard label="Con hoja de resultado" value={n(summary.withResult)} />
        <KpiCard label="Cobradas sin resultado" value={n(summary.chargedWithoutResult)} />
      </div>
      <ListFilterBar
        searchValue={firstParam(sp.q)}
        searchPlaceholder="Factura o paciente (mín. 2)"
        searchLabel="Buscar"
        clearHref={hasActiveFilters(params) ? "/estudios" : undefined}
        activeChips={chips}
        chipGroups={[
          {
            param: "familia",
            label: "Estudio",
            value: family,
            allHref: buildListHref("/estudios", baseWithoutFamily),
            options: summary.families.map((item) => ({
              value: item.id,
              label: item.label,
              count: item.n,
              href: buildListHref("/estudios", { ...baseWithoutFamily, familia: item.id }),
            })),
          },
        ]}
      />
      <ResultCount shown={list.rows.length} total={list.total} page={list.page} pageSize={DEFAULT_PAGE_SIZE} />
      {list.rows.length === 0 ? (
        <EmptyState
          title="No se encontraron estudios"
          hint="Prueba otro término o quita el filtro de familia."
        />
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
      <Pagination page={list.page} pageSize={DEFAULT_PAGE_SIZE} total={list.total} shown={list.rows.length} basePath="/estudios" searchParams={params} />
    </div>
  );
}
