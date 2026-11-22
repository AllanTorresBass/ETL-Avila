import { BreakdownCard, type BreakdownRow } from "@/components/breakdown-card";
import { DonutChart } from "@/components/donut-chart";
import { EmptyState } from "@/components/empty-state";
import { Meter } from "@/components/meter";
import { SectionCard } from "@/components/section-card";
import { TrendChart } from "@/components/trend-chart";
import { getAuthorizationAnalytics, type AuthGroupRow } from "@/lib/authorization-data";
import {
  AUTH_DATE_SOURCE_LABELS,
  AUTH_ESTADO_LABELS,
  AUTH_LAG_BUCKETS,
  AUTH_STATUS_LABELS,
} from "@/lib/authorization-labels";
import { formatPercent, formatUsdCompact } from "@/lib/format-metrics";
import { buildListHref } from "@/lib/list-params";

const n = (v: number) => v.toLocaleString("es-VE");

function listHref(param: string, value: string): string | undefined {
  return value ? `${buildListHref("/autorizaciones", { [param]: value })}#lista` : undefined;
}

function groupRows(rows: AuthGroupRow[], param: string): BreakdownRow[] {
  return rows.map((r) => ({
    key: r.key || r.label,
    label: r.label,
    value: r.lines,
    display: `${n(r.lines)} · ${formatPercent(r.lines > 0 ? r.linked / r.lines : 0)} con factura`,
    hint: r.usd > 0 ? formatUsdCompact(r.usd) : undefined,
    href: listHref(param, r.key),
  }));
}

/** Analysis view: how lines flow to a factura, where they stall, and why. */
export async function AuthorizationAnalyticsView({ months }: { months: number }) {
  const data = await getAuthorizationAnalytics(months).catch(() => null);
  if (!data) {
    return (
      <EmptyState
        title="No se pudo cargar el análisis"
        hint="Revisa la conexión a Neon y vuelve a cargar la página."
      />
    );
  }
  const { funnel } = data;
  if (funnel.lines === 0) {
    return (
      <EmptyState
        title="Sin autorizaciones en este periodo"
        hint="Elige un periodo más amplio. Las líneas sin fecha solo aparecen en «Todo»."
      />
    );
  }

  const statusRows: BreakdownRow[] = data.statuses.map((s) => {
    const estado = s.key === "review" ? "revision" : s.key;
    return {
      key: s.key,
      label: AUTH_STATUS_LABELS[s.key] ?? "Sin evaluar",
      value: s.n,
      display: n(s.n),
      href: estado in AUTH_ESTADO_LABELS ? listHref("estado", estado) : undefined,
    };
  });
  const lagByKey = new Map(data.lag.map((r) => [r.key, r.n]));
  const lagRows: BreakdownRow[] = AUTH_LAG_BUCKETS.map((b) => ({
    key: b.key,
    label: b.label,
    value: lagByKey.get(b.key) ?? 0,
    display: n(lagByKey.get(b.key) ?? 0),
  }));
  const lagTotal = lagRows.reduce((sum, r) => sum + r.value, 0);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title="Del libro a la factura"
          description="Cada paso depende del anterior: sin persona o sin fecha, el emparejador tiene menos señales."
        >
          <div className="space-y-4">
            <Meter label="Identifican paciente o titular" value={funnel.withPerson} total={funnel.lines} />
            <Meter
              label="Tienen fecha o mes"
              value={funnel.withDate}
              total={funnel.lines}
              href={listHref("fecha", "sin")}
            />
            <Meter
              label="Tienen fecha exacta"
              value={funnel.withExactDate}
              total={funnel.lines}
              href={listHref("fecha", "periodo")}
            />
            <Meter
              label="Vinculadas a una factura"
              value={funnel.linked}
              total={funnel.lines}
              href={listHref("estado", "pendiente")}
            />
          </div>
        </SectionCard>
        <BreakdownCard
          title="Por qué no tienen factura"
          description="Motivo guardado por el emparejador en cada línea sin factura."
          rows={statusRows}
          empty="Todas las líneas del periodo tienen factura."
        />
      </div>

      <SectionCard title="Evolución mensual" description="Por fecha exacta o, si falta, por el mes del archivo.">
        <TrendChart data={data.trend} countLabel="Autorizaciones" />
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <BreakdownCard
          title="Por aseguradora"
          description="Líneas, porcentaje con factura y monto solicitado."
          rows={groupRows(data.insurers, "aseguradora")}
          empty="Sin aseguradoras en el periodo."
        />
        <BreakdownCard
          title="Contratantes principales"
          rows={groupRows(data.contratantes, "contratante")}
          empty="Sin contratantes en el periodo."
        />
        <BreakdownCard
          title="Especialidades principales"
          rows={groupRows(data.especialidades, "especialidad")}
          empty="Sin especialidad asignada en el periodo."
        />
        <BreakdownCard
          title="Días hasta la factura"
          description={
            lagTotal > 0
              ? `${n(lagTotal)} líneas con fecha exacta y factura.`
              : "Ninguna línea del periodo tiene fecha exacta y factura."
          }
          rows={lagTotal > 0 ? lagRows : []}
          empty="Sin datos de tiempo en el periodo."
        />
      </div>

      <SectionCard title="De dónde sale la fecha" description="Columna del libro, o el mes del nombre del archivo u hoja.">
        <DonutChart
          centerLabel="líneas"
          slices={data.dateSources.map((s) => ({
            key: s.key,
            label: AUTH_DATE_SOURCE_LABELS[s.key] ?? s.key,
            value: s.n,
          }))}
        />
      </SectionCard>
    </div>
  );
}
