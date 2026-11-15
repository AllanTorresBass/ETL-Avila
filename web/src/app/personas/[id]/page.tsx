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

export default async function PersonaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const db = sql();
  const [person] = await db`
    SELECT id, identity_type::text AS identity_type, identity_number, full_name
    FROM avila.person WHERE id = ${id}::uuid
  `;
  if (!person) notFound();

  const invoices = await db`
    SELECT i.id, i.invoice_number, ip.role::text AS role, a.legal_name AS account
    FROM avila.invoice_person ip
    JOIN avila.invoice i ON i.id = ip.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE ip.person_id = ${id}::uuid
    ORDER BY i.invoice_number
  `;
  const docs = await db`
    SELECT id, page_index, document_type::text AS document_type, upload_status::text AS upload_status
    FROM avila.document
    WHERE person_id = ${id}::uuid
    ORDER BY page_index
  `;

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/personas", label: "Personas" },
          { label: person.full_name || person.identity_number || "Persona" },
        ]}
      />
      <PageHeader
        eyebrow="Persona"
        title={person.full_name || "Sin nombre"}
        description={`${person.identity_type}: ${person.identity_number || "—"}`}
      />

      <Card className="rounded-3xl border-slate-100 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-medium">Facturas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {invoices.length === 0 ? (
            <p className="text-sm text-slate-500">Sin facturas vinculadas todavía.</p>
          ) : (
            invoices.map((inv) => (
              <Link
                key={inv.id}
                href={`/facturas/${inv.id}`}
                className="flex justify-between text-sm hover:text-[#033CA0]"
              >
                <span>{formatInvoiceNumber(inv.invoice_number)}</span>
                <span className="text-slate-500">
                  {inv.role} · {formatAccount(inv.account)}
                </span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-xl font-medium">Documentos personales</h2>
        {docs.length === 0 ? (
          <EmptyState
            title="Sin documentos para esta persona"
            hint="La carga puede no haber vinculado páginas aún."
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
