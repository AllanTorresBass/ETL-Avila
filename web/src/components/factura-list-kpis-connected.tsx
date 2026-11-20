"use client";

import { useSearchParams } from "next/navigation";
import {
  FacturaListKpisStrip,
  type FacturaListFilterState,
} from "@/components/factura-list-kpis";
import type { FacturaListKpis } from "@/lib/factura-data";

function pick(sp: URLSearchParams, key: string): string | undefined {
  const v = sp.get(key);
  return v && v.length > 0 ? v : undefined;
}

/** Keeps KPI cards wired to the current URL filters without re-fetching corpus metrics. */
export function FacturaListKpisConnected({ kpis }: { kpis: FacturaListKpis }) {
  const sp = useSearchParams();
  const filters: FacturaListFilterState = {
    has_person: pick(sp, "has_person"),
    has_titular: pick(sp, "has_titular"),
    has_docs: pick(sp, "has_docs"),
  };

  return <FacturaListKpisStrip kpis={kpis} filters={filters} />;
}
