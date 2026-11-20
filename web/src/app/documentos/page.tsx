import { EmptyState } from "@/components/empty-state";
import { DocumentCard } from "@/components/document-card";
import { ListFilterBar } from "@/components/list-filter-bar";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { queryDocumentoList } from "@/lib/document-data";
import { DOCUMENT_TYPE_LABELS, UPLOAD_STATUS_LABELS } from "@/lib/db";
import { formatInvoiceNumber } from "@/lib/format";
import {
  buildListHref,
  firstParam,
  hasActiveFilters,
  normalizeQuery,
  omitParam,
  type ActiveChip,
} from "@/lib/list-params";

export const dynamic = "force-dynamic";

const UPLOAD_STATUSES = ["pending", "uploaded", "failed", "skipped"] as const;

export default async function DocumentosPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    type?: string;
    upload_status?: string;
    account?: string;
    page?: string;
  }>;
}) {
  const sp = await searchParams;
  const query = normalizeQuery(sp.q);
  const rawQ = firstParam(sp.q);
  const type = firstParam(sp.type);
  const uploadStatus = firstParam(sp.upload_status);
  const account = firstParam(sp.account);
  const requestedPage = parsePage(firstParam(sp.page) || undefined);

  const typeOk = type in DOCUMENT_TYPE_LABELS ? type : "";
  const statusOk = (UPLOAD_STATUSES as readonly string[]).includes(uploadStatus)
    ? uploadStatus
    : "";

  const { accounts, types, statusCounts, total, page, docs } = await queryDocumentoList({
    typeOk,
    statusOk,
    account,
    query,
    pageSize: DEFAULT_PAGE_SIZE,
    requestedPage,
  });

  const filterParams: Record<string, string | undefined> = {
    q: query || undefined,
    type: typeOk || undefined,
    upload_status: statusOk || undefined,
    account: account || undefined,
  };

  const baseWithoutType = { ...filterParams, type: undefined, page: undefined };
  const baseWithoutStatus = { ...filterParams, upload_status: undefined, page: undefined };

  const activeChips: ActiveChip[] = [];
  if (query) {
    activeChips.push({
      key: "q",
      label: `Buscar: ${query}`,
      clearHref: buildListHref("/documentos", omitParam(filterParams, "q")),
    });
  }
  if (typeOk) {
    activeChips.push({
      key: "type",
      label: DOCUMENT_TYPE_LABELS[typeOk] || typeOk,
      clearHref: buildListHref("/documentos", omitParam(filterParams, "type")),
    });
  }
  if (statusOk) {
    activeChips.push({
      key: "upload_status",
      label: UPLOAD_STATUS_LABELS[statusOk] || statusOk,
      clearHref: buildListHref("/documentos", omitParam(filterParams, "upload_status")),
    });
  }
  if (account) {
    const accName = accounts.find((a) => a.code === account)?.legal_name || account;
    activeChips.push({
      key: "account",
      label: accName,
      clearHref: buildListHref("/documentos", omitParam(filterParams, "account")),
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documentos"
        description="Una tarjeta por página, con tipo y enlace único."
      />
      <ListFilterBar
        searchValue={rawQ}
        searchPlaceholder="Factura o evidencia (mín. 2)"
        searchLabel="Buscar"
        clearHref={hasActiveFilters(filterParams) ? "/documentos" : undefined}
        activeChips={activeChips}
        selects={[
          {
            name: "account",
            label: "Cuenta",
            value: account,
            emptyLabel: "Todas las cuentas",
            options: accounts.map((a) => ({ value: a.code, label: a.legal_name })),
          },
        ]}
        chipGroups={[
          {
            param: "type",
            label: "Tipo",
            value: typeOk,
            allHref: buildListHref("/documentos", baseWithoutType),
            options: types.map((t) => ({
              value: t.document_type,
              label: DOCUMENT_TYPE_LABELS[t.document_type] || t.document_type,
              count: t.n,
              href: buildListHref("/documentos", {
                ...baseWithoutType,
                type: t.document_type,
              }),
            })),
          },
          {
            param: "upload_status",
            label: "Estado Blob",
            value: statusOk,
            allHref: buildListHref("/documentos", baseWithoutStatus),
            options: statusCounts.map((s) => ({
              value: s.upload_status,
              label: UPLOAD_STATUS_LABELS[s.upload_status] || s.upload_status,
              count: s.n,
              href: buildListHref("/documentos", {
                ...baseWithoutStatus,
                upload_status: s.upload_status,
              }),
            })),
          },
        ]}
      />
      <ResultCount
        shown={docs.length}
        total={total}
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
      />
      {docs.length === 0 ? (
        <EmptyState
          title="No se encontraron documentos"
          hint="Cambia el tipo, el estado o la búsqueda, o ejecuta la carga hacia Neon y Blob."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {docs.map((doc) => (
            <DocumentCard
              key={doc.id}
              id={doc.id}
              documentType={doc.document_type}
              pageIndex={doc.page_index}
              uploadStatus={doc.upload_status}
              subtitle={formatInvoiceNumber(doc.invoice_number)}
            />
          ))}
        </div>
      )}
      <Pagination
        page={page}
        pageSize={DEFAULT_PAGE_SIZE}
        total={total}
        shown={docs.length}
        basePath="/documentos"
        searchParams={filterParams}
      />
    </div>
  );
}
