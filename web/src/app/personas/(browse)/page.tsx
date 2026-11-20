import { Suspense } from "react";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PersonasFilterSkeleton, PersonasListSkeleton } from "@/components/personas-page-skeleton";
import { PersonasResults } from "@/components/personas-results";
import { ScrollToAnchor } from "@/components/scroll-to-anchor";
import { ROLE_LABELS, sql } from "@/lib/db";
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

async function PersonasFilterSection({
  sp,
}: {
  sp: {
    q?: string;
    has_ci?: string;
    has_phone?: string;
    has_invoice?: string;
    has_contact_gap?: string;
    incomplete_name?: string;
    role?: string;
    account?: string;
    page?: string;
  };
}) {
  const query = normalizeQuery(sp.q);
  const rawQ = firstParam(sp.q);
  const hasCi = triState(sp.has_ci);
  const hasPhone = triState(sp.has_phone);
  const hasInvoice = triState(sp.has_invoice);
  const hasContactGap = triState(sp.has_contact_gap);
  const incompleteName = triState(sp.incomplete_name);
  const role = firstParam(sp.role);
  const account = firstParam(sp.account);
  const db = sql();

  const roleOk = role === "titular" || role === "beneficiario" || role === "unknown";
  const roleFilter = roleOk ? role : "";
  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    has_ci: hasCi || undefined,
    has_phone: hasPhone || undefined,
    has_invoice: hasInvoice || undefined,
    has_contact_gap: hasContactGap || undefined,
    incomplete_name: incompleteName || undefined,
    role: roleFilter || undefined,
    account: account || undefined,
  };
  const filtersActive = hasActiveFilters(filterParams);

  const accounts = await db`SELECT code, legal_name FROM avila.account ORDER BY legal_name`;

  const activeChips: ActiveChip[] = [];
  if (query) {
    activeChips.push({
      key: "q",
      label: `Buscar: ${query}`,
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "q"))}#lista`,
    });
  }
  if (hasCi === "1") {
    activeChips.push({
      key: "has_ci",
      label: "Con cédula",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_ci"))}#lista`,
    });
  } else if (hasCi === "0") {
    activeChips.push({
      key: "has_ci",
      label: "Sin cédula",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_ci"))}#lista`,
    });
  }
  if (hasPhone === "1") {
    activeChips.push({
      key: "has_phone",
      label: "Con teléfono",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_phone"))}#lista`,
    });
  } else if (hasPhone === "0") {
    activeChips.push({
      key: "has_phone",
      label: "Sin teléfono",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_phone"))}#lista`,
    });
  }
  if (hasInvoice === "1") {
    activeChips.push({
      key: "has_invoice",
      label: "Con factura",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_invoice"))}#lista`,
    });
  } else if (hasInvoice === "0") {
    activeChips.push({
      key: "has_invoice",
      label: "Sin factura",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_invoice"))}#lista`,
    });
  }
  if (hasContactGap === "1") {
    activeChips.push({
      key: "has_contact_gap",
      label: "Gaps de contacto",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "has_contact_gap"))}#lista`,
    });
  }
  if (incompleteName === "1") {
    activeChips.push({
      key: "incomplete_name",
      label: "Nombre incompleto",
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "incomplete_name"))}#lista`,
    });
  }
  if (roleFilter) {
    activeChips.push({
      key: "role",
      label: ROLE_LABELS[roleFilter] || roleFilter,
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "role"))}#lista`,
    });
  }
  if (account) {
    const accName = accounts.find((a) => a.code === account)?.legal_name || account;
    activeChips.push({
      key: "account",
      label: accName,
      clearHref: `${buildListHref("/personas", omitParam(filterParams, "account"))}#lista`,
    });
  }

  const clearHref = filtersActive ? "/personas#lista" : undefined;

  return (
    <ListFilterBar
      searchValue={rawQ}
      searchPlaceholder="Cédula, nombre, teléfono o clave (mín. 2)"
      searchLabel="Buscar"
      clearHref={clearHref}
      hash="lista"
      activeChips={activeChips}
      selects={[
        {
          name: "has_ci",
          label: "Cédula",
          value: hasCi,
          emptyLabel: "Todas",
          options: [
            { value: "1", label: "Con cédula" },
            { value: "0", label: "Sin cédula" },
          ],
        },
        {
          name: "has_phone",
          label: "Teléfono",
          value: hasPhone,
          emptyLabel: "Todos",
          options: [
            { value: "1", label: "Con teléfono" },
            { value: "0", label: "Sin teléfono" },
          ],
        },
        {
          name: "has_invoice",
          label: "Factura",
          value: hasInvoice,
          emptyLabel: "Todas",
          options: [
            { value: "1", label: "Con factura" },
            { value: "0", label: "Sin factura" },
          ],
        },
        {
          name: "has_contact_gap",
          label: "Contacto",
          value: hasContactGap,
          emptyLabel: "Todos",
          options: [{ value: "1", label: "Con gaps de contacto" }],
        },
        {
          name: "incomplete_name",
          label: "Nombre",
          value: incompleteName,
          emptyLabel: "Todos",
          options: [{ value: "1", label: "Nombre incompleto" }],
        },
        {
          name: "role",
          label: "Rol en factura",
          value: roleFilter,
          emptyLabel: "Todos los roles",
          options: [
            { value: "titular", label: ROLE_LABELS.titular },
            { value: "beneficiario", label: ROLE_LABELS.beneficiario },
            { value: "unknown", label: ROLE_LABELS.unknown },
          ],
        },
        {
          name: "account",
          label: "Cuenta",
          value: account,
          emptyLabel: "Todas las cuentas",
          options: accounts.map((a) => ({ value: a.code, label: a.legal_name })),
        },
      ]}
    />
  );
}

export default async function PersonasPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    has_ci?: string;
    has_phone?: string;
    has_invoice?: string;
    has_contact_gap?: string;
    incomplete_name?: string;
    role?: string;
    account?: string;
    page?: string;
  }>;
}) {
  const sp = await searchParams;
  const listKey = JSON.stringify({
    q: firstParam(sp.q),
    has_ci: firstParam(sp.has_ci),
    has_phone: firstParam(sp.has_phone),
    has_invoice: firstParam(sp.has_invoice),
    has_contact_gap: firstParam(sp.has_contact_gap),
    incomplete_name: firstParam(sp.incomplete_name),
    role: firstParam(sp.role),
    account: firstParam(sp.account),
    page: firstParam(sp.page) || "1",
  });

  return (
    <div className="space-y-6">
      <Suspense fallback={null}>
        <ScrollToAnchor id="lista" />
      </Suspense>

      <Suspense fallback={<PersonasFilterSkeleton />}>
        <PersonasFilterSection sp={sp} />
      </Suspense>

      <Suspense key={listKey} fallback={<PersonasListSkeleton />}>
        <PersonasResults sp={sp} />
      </Suspense>
    </div>
  );
}
