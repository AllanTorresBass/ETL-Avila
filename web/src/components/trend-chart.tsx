"use client";

import { useState } from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { formatCompact, formatMonthKey, formatUsd, formatUsdCompact } from "@/lib/format-metrics";

type Point = { month: string; usd: number; invoices: number };
type Metric = "usd" | "invoices";

/** `countLabel` names the `invoices` series (facturas on BI, autorizaciones elsewhere). */
export function TrendChart({ data, countLabel = "Facturas" }: { data: Point[]; countLabel?: string }) {
  const [metric, setMetric] = useState<Metric>("usd");
  const hasSignal = data.some((p) => p[metric] > 0);
  const metrics: { id: Metric; label: string }[] = [
    { id: "usd", label: "Monto USD" },
    { id: "invoices", label: countLabel },
  ];
  const config = {
    usd: { label: "Monto USD", color: "var(--chart-1)" },
    invoices: { label: countLabel, color: "var(--chart-2)" },
  } satisfies ChartConfig;

  return (
    <div>
      <div role="group" aria-label="Métrica del gráfico" className="mb-4 inline-flex gap-1 rounded-full bg-muted p-1">
        {metrics.map((m) => (
          <button
            key={m.id}
            type="button"
            aria-pressed={metric === m.id}
            onClick={() => setMetric(m.id)}
            className={`min-h-9 rounded-full px-4 text-sm font-medium transition-colors ${
              metric === m.id ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {data.length === 0 || !hasSignal ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-border text-sm text-muted-foreground">
          Sin datos para este periodo.
        </div>
      ) : (
        <>
          <ChartContainer config={config} className="h-64 w-full" role="img" aria-label={`Evolución mensual de ${config[metric].label}`}>
            <AreaChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={`var(--color-${metric})`} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={`var(--color-${metric})`} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={24}
                tickFormatter={formatMonthKey}
              />
              <YAxis
                width={52}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => (metric === "usd" ? formatUsdCompact(v) : formatCompact(v))}
              />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    labelFormatter={(_, payload) => formatMonthKey(String(payload?.[0]?.payload?.month ?? ""))}
                    formatter={(value) => (
                      <span className="font-mono font-medium tabular-nums">
                        {metric === "usd" ? formatUsd(Number(value)) : Number(value).toLocaleString("es-VE")}
                      </span>
                    )}
                  />
                }
              />
              <Area
                dataKey={metric}
                type="monotone"
                stroke={`var(--color-${metric})`}
                strokeWidth={2}
                fill="url(#trend-fill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ChartContainer>
          <table className="sr-only">
            <caption>Evolución mensual</caption>
            <thead>
              <tr>
                <th scope="col">Mes</th>
                <th scope="col">Monto USD</th>
                <th scope="col">{countLabel}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.month}>
                  <th scope="row">{formatMonthKey(p.month)}</th>
                  <td>{formatUsd(p.usd)}</td>
                  <td>{p.invoices}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
