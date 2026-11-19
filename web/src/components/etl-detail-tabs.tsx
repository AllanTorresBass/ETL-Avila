"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type EtlDetailPanel = {
  id: string;
  label: string;
  count: string;
  title: string;
  description: string;
  body: React.ReactNode;
};

/** Switches the four ETL inventories without leaving the operations summary above. */
export function EtlDetailTabs({ panels }: { panels: EtlDetailPanel[] }) {
  const first = panels[0]?.id ?? "revision";

  return (
    <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <Tabs defaultValue={first}>
        <TabsList
          aria-label="Detalle operativo"
          className="!h-auto w-full flex-wrap items-center justify-start gap-1 rounded-full border border-border bg-muted p-1"
        >
          {panels.map((panel) => (
            <TabsTrigger
              key={panel.id}
              value={panel.id}
              className="h-auto min-h-9 flex-1 rounded-full px-3 sm:flex-none"
            >
              {panel.label}
              <span className="tabular-nums text-xs text-muted-foreground">{panel.count}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        {panels.map((panel) => (
          <TabsContent key={panel.id} value={panel.id} className="mt-5 outline-none">
            <h2 className="text-lg font-semibold text-foreground">{panel.title}</h2>
            <p className="mt-0.5 mb-4 text-sm text-muted-foreground">{panel.description}</p>
            {panel.body}
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
