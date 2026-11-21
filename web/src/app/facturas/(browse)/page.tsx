import { Suspense } from "react";
import { FacturasFilterSkeleton, FacturasListSkeleton } from "@/components/facturas-page-skeleton";
import { FacturasResults } from "@/components/facturas-results";
import { ListFilterBar } from "@/components/list-filter-bar";
import { ScrollToAnchor } from "@/components/scroll-to-anchor";
import { listAccounts, listInvoiceMonths, listInvoiceYears } from "@/lib/account-data";
import {
  buildListHref,
  firstParam,
  hasActiveFilters,
  normalizeQuery,
  omitParam,
  triState,
  type ActiveChip,
} from "@/lib/list-params";

export const dynamic = "force-dynamic";

async function FacturasFilterSection({
  sp,
}: {
  sp: {
    q?: string;
    account?: string;
    year?: string;
    month?: string;
    has_person?: string;
    has_titular?: string;
    has_docs?: string;
    role_gap?: string;
    page?: string;
  };
}) {
  const query = normalizeQuery(sp.q);
  const rawQ = firstParam(sp.q);
  const account = firstParam(sp.account);
  const year = firstParam(sp.year);
  const month = firstParam(sp.month);
  const hasPerson = triState(sp.has_person);
  const hasTitular = triState(sp.has_titular);
  const hasDocs = triState(sp.has_docs);
  const roleGapRaw = firstParam(sp.role_gap);
  const roleGap = ["mismatch", "no_ci", "nameless", "blocked", "multi"].includes(roleGapRaw)
    ? roleGapRaw
    : "";

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    account: account || undefined,
    year: year || undefined,
    month: month || undefined,
    has_person: hasPerson || undefined,
    has_titular: hasTitular || undefined,
    has_docs: hasDocs || undefined,
    role_gap: roleGap || undefined,
  };
  const filtersActive = hasActiveFilters(filterParams);

  const [accounts, years, months] = await Promise.all([
    listAccounts(),
    listInvoiceYears(),
    listInvoiceMonths(),
  ]);

  const activeChips: ActiveChip[] = [];
  if (query) {
    activeChips.push({
      key: "q",
      label: `Nº ${query}`,
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "q"))}#lista`,
    });
  }
  if (account) {
    const accName = accounts.find((a) => a.code === account)?.legal_name || account;
    activeChips.push({
      key: "account",
      label: accName,
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "account"))}#lista`,
    });
  }
  if (year) {
    activeChips.push({
      key: "year",
      label: `Año ${year}`,
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "year"))}#lista`,
    });
  }
  if (month) {
    activeChips.push({
      key: "month",
      label: `Mes ${month}`,
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "month"))}#lista`,
    });
  }
  if (hasPerson === "1") {
    activeChips.push({
      key: "has_person",
      label: "Con persona",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_person"))}#lista`,
    });
  } else if (hasPerson === "0") {
    activeChips.push({
      key: "has_person",
      label: "Sin persona",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_person"))}#lista`,
    });
  }
  if (hasTitular === "1") {
    activeChips.push({
      key: "has_titular",
      label: "Con titular",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_titular"))}#lista`,
    });
  } else if (hasTitular === "0") {
    activeChips.push({
      key: "has_titular",
      label: "Sin titular",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_titular"))}#lista`,
    });
  }
  if (hasDocs === "1") {
    activeChips.push({
      key: "has_docs",
      label: "Con documentos",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_docs"))}#lista`,
    });
  } else if (hasDocs === "0") {
    activeChips.push({
      key: "has_docs",
      label: "Sin documentos",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "has_docs"))}#lista`,
    });
  }
  if (roleGap === "mismatch") {
    activeChips.push({
      key: "role_gap",
      label: "Paciente ≠ titular sin beneficiario",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "role_gap"))}#lista`,
    });
  } else if (roleGap === "no_ci") {
    activeChips.push({
      key: "role_gap",
      label: "ID sin cédula",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "role_gap"))}#lista`,
    });
  } else if (roleGap === "nameless") {
    activeChips.push({
      key: "role_gap",
      label: "Titular sin nombre",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "role_gap"))}#lista`,
    });
  } else if (roleGap === "blocked") {
    activeChips.push({
      key: "role_gap",
      label: "Rol bloqueado en revisión",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "role_gap"))}#lista`,
    });
  } else if (roleGap === "multi") {
    activeChips.push({
      key: "role_gap",
      label: "Varios titulares",
      clearHref: `${buildListHref("/facturas", omitParam(filterParams, "role_gap"))}#lista`,
    });
  }

  return (
    <ListFilterBar
      searchValue={rawQ}
      searchPlaceholder="Número de factura (mín. 2)"
      searchLabel="Número"
      clearHref={filtersActive ? "/facturas#lista" : undefined}
      hash="lista"
      activeChips={activeChips}
      selects={[
        {
          name: "account",
          label: "Cuenta",
          value: account,
          emptyLabel: "Todas las cuentas",
          options: accounts.map((a) => ({ value: a.code, label: a.legal_name })),
        },
        {
          name: "year",
          label: "Año",
          value: year,
          emptyLabel: "Todos",
          options: years
            .filter((r) => r.y)
            .map((r) => ({ value: String(r.y), label: String(r.y) })),
        },
        {
          name: "month",
          label: "Mes",
          value: month,
          emptyLabel: "Todos",
          options: months
            .filter((r) => r.m)
            .map((r) => ({ value: String(r.m), label: String(r.m) })),
        },
        {
          name: "has_person",
          label: "Persona",
          value: hasPerson,
          emptyLabel: "Todas",
          options: [
            { value: "1", label: "Con persona" },
            { value: "0", label: "Sin persona" },
          ],
        },
        {
          name: "has_titular",
          label: "Titular",
          value: hasTitular,
          emptyLabel: "Todos",
          options: [
            { value: "1", label: "Con titular" },
            { value: "0", label: "Sin titular" },
          ],
        },
        {
          name: "has_docs",
          label: "Documentos",
          value: hasDocs,
          emptyLabel: "Todos",
          options: [
            { value: "1", label: "Con documentos" },
            { value: "0", label: "Sin documentos" },
          ],
        },
        {
          name: "role_gap",
          label: "Brecha de rol",
          value: roleGap,
          emptyLabel: "Todas",
          options: [
            { value: "mismatch", label: "Paciente ≠ titular" },
            { value: "no_ci", label: "ID sin cédula" },
            { value: "nameless", label: "Titular sin nombre" },
            { value: "blocked", label: "Bloqueado en revisión" },
            { value: "multi", label: "Varios titulares" },
          ],
        },
      ]}
    />
  );
}

export default async function FacturasPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    account?: string;
    year?: string;
    month?: string;
    has_person?: string;
    has_titular?: string;
    has_docs?: string;
    role_gap?: string;
    page?: string;
  }>;
}) {
  const sp = await searchParams;
  const listKey = JSON.stringify({
    q: firstParam(sp.q),
    account: firstParam(sp.account),
    year: firstParam(sp.year),
    month: firstParam(sp.month),
    has_person: firstParam(sp.has_person),
    has_titular: firstParam(sp.has_titular),
    has_docs: firstParam(sp.has_docs),
    role_gap: firstParam(sp.role_gap),
    page: firstParam(sp.page) || "1",
  });

  return (
    <div className="space-y-6">
      <Suspense fallback={null}>
        <ScrollToAnchor id="lista" />
      </Suspense>

      <div className="facturas-no-print">
        <Suspense fallback={<FacturasFilterSkeleton />}>
          <FacturasFilterSection sp={sp} />
        </Suspense>
      </div>

      <Suspense key={listKey} fallback={<FacturasListSkeleton />}>
        <FacturasResults sp={sp} />
      </Suspense>
    </div>
  );
}
