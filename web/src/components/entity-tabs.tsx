"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type EntityTabPanel = {
  id: string;
  label: string;
  count?: string;
  title: string;
  description?: string;
  body: React.ReactNode;
};

function readHashTab(validIds: Set<string>): string | null {
  if (typeof window === "undefined") return null;
  const raw = window.location.hash.replace(/^#/, "");
  // Legacy deep links used section ids like "titulares" / "beneficiarios" / "expediente".
  const mapped =
    raw === "titulares" || raw === "beneficiarios"
      ? "red"
      : raw === "expediente"
        ? "facturas"
        : raw;
  return validIds.has(mapped) ? mapped : null;
}

/** URL-aware tab switcher for entity dossiers (persona, etc.). Syncs `?tab=` and honors legacy `#hash`. */
export function EntityTabs({
  panels,
  defaultValue,
  ariaLabel = "Secciones",
  paramName = "tab",
}: {
  panels: EntityTabPanel[];
  /** Server-resolved default when neither `?tab=` nor hash applies. */
  defaultValue: string;
  ariaLabel?: string;
  paramName?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();
  const panelIds = panels.map((p) => p.id).join("|");
  const validIds = new Set(panels.map((p) => p.id));

  const fromQuery = searchParams.get(paramName);
  const initial =
    fromQuery && validIds.has(fromQuery)
      ? fromQuery
      : validIds.has(defaultValue)
        ? defaultValue
        : (panels[0]?.id ?? "facturas");

  const [value, setValue] = useState(initial);

  useEffect(() => {
    const fromHash = readHashTab(new Set(panelIds.split("|").filter(Boolean)));
    if (!fromHash) return;
    setValue(fromHash);
    const next = new URLSearchParams(searchParams.toString());
    next.set(paramName, fromHash);
    startTransition(() => {
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    });
    // Mount-only: honor legacy #hash deep links once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const q = searchParams.get(paramName);
    if (q && panelIds.split("|").includes(q) && q !== value) setValue(q);
  }, [paramName, searchParams, panelIds, value]);

  const onValueChange = useCallback(
    (nextId: string) => {
      setValue(nextId);
      const next = new URLSearchParams(searchParams.toString());
      next.set(paramName, nextId);
      startTransition(() => {
        router.replace(`${pathname}?${next.toString()}`, { scroll: false });
      });
    },
    [paramName, pathname, router, searchParams, startTransition],
  );

  if (panels.length === 0) return null;

  return (
    <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
      <Tabs value={value} onValueChange={onValueChange}>
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
