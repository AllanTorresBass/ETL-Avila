import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { DocumentCard } from "@/components/document-card";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { sql } from "@/lib/db";
import { formatAccount, formatInvoiceNumber } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function FacturaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const db = sql();
  const [invoice] = await db`
    SELECT i.*, a.legal_name AS account
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE i.id = ${id}::uuid
  `;
  if (!invoice) notFound();

  const people = await db`
    SELECT p.id, p.identity_number, p.full_name, ip.role::text AS role
    FROM avila.invoice_person ip
    JOIN avila.person p ON p.id = ip.person_id
    WHERE ip.invoice_id = ${id}::uuid
  `;
  const files = await db`
    SELECT id, file_label, extension, pages, rule_id
    FROM avila.source_file WHERE invoice_id = ${id}::uuid
    ORDER BY created_at
  `;
  const docs = await db`
    SELECT id, page_index, document_type::text AS document_type, upload_status::text AS upload_status
    FROM avila.document WHERE invoice_id = ${id}::uuid
    ORDER BY page_index, document_type
  `;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/facturas", label: "Facturas" },
          { label: formatInvoiceNumber(invoice.invoice_number) },
        ]}
      />
      <PageHeader
        eyebrow="Factura"
        title={formatInvoiceNumber(invoice.invoice_number)}
        description={`${formatAccount(invoice.account)} · ${invoice.month || "—"} ${invoice.year || ""} · lote ${invoice.lote || "—"}`}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="rounded-3xl border-slate-100 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium">Personas</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {people.length === 0 ? (
              <p className="text-slate-500">Sin personas resueltas aún.</p>
            ) : (
              people.map((p) => (
                <Link
                  key={p.id}
                  href={`/personas/${p.id}`}
                  className="flex justify-between hover:text-[#033CA0]"
                >
                  <span>{p.full_name || p.identity_number || p.id.slice(0, 8)}</span>
                  <span className="text-slate-500">{p.role}</span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
        <Card className="rounded-3xl border-slate-100 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium">Archivos fuente</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {files.length === 0 ? (
              <p className="text-slate-500">Sin archivos fuente vinculados.</p>
            ) : (
              files.map((f) => (
                <div key={f.id} className="flex justify-between gap-3">
                  <span>
                    {f.file_label} {f.extension}
                  </span>
                  <span className="text-slate-500">
                    {f.pages || "?"} pág · {f.rule_id}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="mb-3 text-xl font-medium">Páginas del paquete</h2>
        {docs.length === 0 ? (
          <EmptyState
            title="Sin páginas en este paquete"
            hint="Ejecuta la carga de documentos para materializar páginas en Blob."
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
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
