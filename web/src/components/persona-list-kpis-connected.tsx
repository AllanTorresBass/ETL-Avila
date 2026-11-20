"use client";

import { useSearchParams } from "next/navigation";
import {
  PersonaListKpisStrip,
  type PersonaListFilterState,
} from "@/components/persona-list-kpis";
import type { PersonaListKpis } from "@/lib/persona-data";

function pick(sp: URLSearchParams, key: string): string | undefined {
  const v = sp.get(key);
  return v && v.length > 0 ? v : undefined;
}

/** Keeps KPI cards wired to the current URL filters without re-fetching corpus metrics. */
export function PersonaListKpisConnected({ kpis }: { kpis: PersonaListKpis }) {
  const sp = useSearchParams();
  const filters: PersonaListFilterState = {
    has_ci: pick(sp, "has_ci"),
    has_phone: pick(sp, "has_phone"),
    has_invoice: pick(sp, "has_invoice"),
    has_contact_gap: pick(sp, "has_contact_gap"),
    incomplete_name: pick(sp, "incomplete_name"),
    role: pick(sp, "role"),
  };

  return <PersonaListKpisStrip kpis={kpis} filters={filters} />;
}
