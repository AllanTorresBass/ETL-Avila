import { Suspense } from "react";
import { PersonaListKpisConnected } from "@/components/persona-list-kpis-connected";
import { getPersonaListKpis } from "@/lib/persona-data";

/** Server fetch for corpus KPIs; active filter state is read on the client. */
export async function PersonaListKpisLoader() {
  const kpis = await getPersonaListKpis();
  return (
    <Suspense fallback={null}>
      <PersonaListKpisConnected kpis={kpis} />
    </Suspense>
  );
}
