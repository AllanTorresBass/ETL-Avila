import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { DocumentCard } from "@/components/document-card";
import { PageHeader } from "@/components/page-header";
import { Pagination, DEFAULT_PAGE_SIZE, parsePage } from "@/components/pagination";
import { ResultCount } from "@/components/result-count";
import { DOCUMENT_TYPE_LABELS, sql } from "@/lib/db";
import { formatInvoiceNumber } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DocumentosPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; page?: string }>;
}) {
  const { type = "", page: pageRaw } = await searchParams;
  const page = parsePage(pageRaw);
  const offset = (page - 1) * DEFAULT_PAGE_SIZE;
  const db = sql();

  const types = await db`
    SELECT document_type::text AS document_type, count(*)::int AS n
    FROM avila.document GROUP BY 1 ORDER BY n DESC
  `;

  const [countRow] = type
    ? await db`
        SELECT count(*)::int AS n FROM avila.document
        WHERE document_type = ${type}::avila.document_type
      `
    : await db`SELECT count(*)::int AS n FROM avila.document`;
  const total = countRow?.n ?? 0;

  const docs = type
    ? await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, i.invoice_number
        FROM avila.document d
        LEFT JOIN avila.invoice i ON i.id = d.invoice_id
        WHERE d.document_type = ${type}::avila.document_type
        ORDER BY d.created_at DESC
        LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
      `
    : await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, i.invoice_number
        FROM avila.document d
        LEFT JOIN avila.invoice i ON i.id = d.invoice_id
        ORDER BY d.created_at DESC
        LIMIT ${DEFAULT_PAGE_SIZE} OFFSET ${offset}
      `;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documentos"
        description="Una tarjeta por página, con tipo y enlace único."
      />
      <div className="flex flex-wrap gap-2">
        <Link
          href="/documentos"
          className={`rounded-full px-3 py-1.5 text-xs font-medium ${
            !type ? "bg-[#033CA0] text-white" : "border border-slate-200 bg-white text-slate-600"
          }`}
        >
          Todos
        </Link>
        {types.map((t) => (
          <Link
            key={t.document_type}
            href={`/documentos?type=${t.document_type}`}
            className={`rounded-full px-3 py-1.5 text-xs font-medium ${
              type === t.document_type
                ? "bg-[#033CA0] text-white"
                : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            {DOCUMENT_TYPE_LABELS[t.document_type] || t.document_type} ({t.n})
          </Link>
        ))}
      </div>
      <ResultCount shown={docs.length} total={total} />
      {docs.length === 0 ? (
        <EmptyState
          title="No se encontraron documentos"
          hint="Ejecuta la carga piloto o completa hacia Neon y Blob."
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
        basePath="/documentos"
        searchParams={{ type: type || undefined }}
      />
    </div>
  );
}
