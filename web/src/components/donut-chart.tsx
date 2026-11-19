"use client";

import { Cell, Pie, PieChart } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";

export type DonutSlice = { key: string; label: string; value: number };

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-5)", "var(--chart-4)", "var(--muted-foreground)"];

/** Keeps the largest slices and folds the long tail into "Otros". */
export function foldSlices(slices: DonutSlice[], keep = 5): DonutSlice[] {
  const sorted = [...slices].sort((a, b) => b.value - a.value);
  if (sorted.length <= keep + 1) return sorted;
  const head = sorted.slice(0, keep);
  const rest = sorted.slice(keep).reduce((sum, s) => sum + s.value, 0);
  return [...head, { key: "otros", label: "Otros", value: rest }];
}

export function DonutChart({
  slices,
  centerLabel,
  keep,
}: {
  slices: DonutSlice[];
  centerLabel: string;
  keep?: number;
}) {
  const shown = keep == null ? slices : foldSlices(slices, keep);
  const total = shown.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">Aún no hay datos para mostrar.</p>;
  }

  const config: ChartConfig = Object.fromEntries(
    shown.map((s, i) => [s.key, { label: s.label, color: COLORS[i % COLORS.length] }]),
  );

  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row">
      <div className="relative size-44 shrink-0">
        <ChartContainer config={config} className="size-44 aspect-square" role="img" aria-label={centerLabel}>
          <PieChart>
            <ChartTooltip content={<ChartTooltipContent hideLabel nameKey="key" />} />
            <Pie
              data={shown}
              dataKey="value"
              nameKey="key"
              innerRadius={54}
              outerRadius={80}
              paddingAngle={2}
              strokeWidth={0}
              isAnimationActive={false}
            >
              {shown.map((s, i) => (
                <Cell key={s.key} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ChartContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold tabular-nums text-foreground">{total.toLocaleString("es-VE")}</span>
          <span className="text-xs text-muted-foreground">{centerLabel}</span>
        </div>
      </div>
      <ul className="w-full min-w-0 flex-1 space-y-2">
        {shown.map((s, i) => (
          <li key={s.key} className="flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden="true"
                className="size-2.5 shrink-0 rounded-full"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className="truncate text-foreground">{s.label}</span>
            </span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {s.value.toLocaleString("es-VE")} · {Math.round((s.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
