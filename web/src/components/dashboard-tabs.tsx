"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type DashboardTabPanel = {
  id: string;
  label: string;
  /** Optional count shown beside the label. */
  count?: string;
  title: string;
  description?: string;
  body: React.ReactNode;
};

/** Primary section switcher for ETL, BI, and Informe dashboards. */
export function DashboardTabs({
  panels,
  ariaLabel = "Secciones del tablero",
}: {
  panels: DashboardTabPanel[];
  ariaLabel?: string;
}) {
  const first = panels[0]?.id ?? "resumen";

  return (
    <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <Tabs defaultValue={first}>
        <TabsList
          aria-label={ariaLabel}
          className="!h-auto w-full flex-wrap items-center justify-start gap-1 rounded-full border border-border bg-muted p-1"
        >
          {panels.map((panel) => (
            <TabsTrigger
              key={panel.id}
              value={panel.id}
              className="h-auto min-h-9 flex-1 rounded-full px-3 sm:flex-none"
            >
              {panel.label}
              {panel.count != null ? (
                <span className="tabular-nums text-xs text-muted-foreground">{panel.count}</span>
              ) : null}
            </TabsTrigger>
          ))}
        </TabsList>

        {panels.map((panel) => (
          <TabsContent key={panel.id} value={panel.id} className="mt-5 outline-none">
            <h2 className="text-lg font-semibold text-foreground">{panel.title}</h2>
            {panel.description ? (
              <p className="mt-0.5 mb-4 text-sm text-muted-foreground">{panel.description}</p>
            ) : (
              <div className="mb-4" />
            )}
            {panel.body}
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
