import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { PageHeader } from "@/components/page-header";
import { UploadStatusBadge } from "@/components/upload-status-badge";
import { DocumentPreview } from "@/components/document-preview";
import { DOCUMENT_TYPE_LABELS, sql } from "@/lib/db";
import { formatInvoiceNumber } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function DocumentoDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const db = sql();
  const [doc] = await db`
    SELECT d.id, d.page_index, d.document_type::text AS document_type, d.evidence,
           d.upload_status::text AS upload_status, d.upload_error, d.blob_url, d.blob_pathname,
           d.invoice_id, d.person_id, i.invoice_number, p.identity_number, p.full_name
    FROM avila.document d
    LEFT JOIN avila.invoice i ON i.id = d.invoice_id
    LEFT JOIN avila.person p ON p.id = d.person_id
    WHERE d.id = ${id}::uuid
  `;
  if (!doc) notFound();

  const typeLabel = DOCUMENT_TYPE_LABELS[doc.document_type] || doc.document_type;
  const canPreview = doc.upload_status === "uploaded" && Boolean(doc.blob_url || doc.blob_pathname);

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/documentos", label: "Documentos" },
          { label: typeLabel },
        ]}
      />
      <PageHeader
        eyebrow="Documento"
        title={typeLabel}
        description={`Página ${doc.page_index}${doc.invoice_number ? ` · ${formatInvoiceNumber(doc.invoice_number)}` : ""}`}
      />

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden rounded-3xl border-slate-100 shadow-sm">
          <CardContent className="p-0">
            {canPreview ? (
              <DocumentPreview src={`/api/blob/${doc.id}`} alt={typeLabel} />
            ) : (
              <div className="flex h-64 flex-col items-center justify-center gap-2 px-6 text-center text-sm text-slate-500">
                <p>Vista no disponible</p>
                <UploadStatusBadge status={doc.upload_status} />
                {doc.upload_status === "failed" ? (
                  <p className="text-xs">
                    Reintenta la carga con el script de upload.
                    {doc.upload_error
                      ? ` ${String(doc.upload_error).split("\n")[0].slice(0, 120)}`
                      : ""}
                  </p>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="rounded-3xl border-slate-100 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium">Detalle</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Tipo</div>
              <Badge
                className={`mt-1 rounded-full ${
                  doc.document_type === "ilegible"
                    ? "bg-amber-50 text-amber-800"
                    : ""
                }`}
              >
                {typeLabel}
              </Badge>
            </div>
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Estado Blob</div>
              <div className="mt-1">
                <UploadStatusBadge status={doc.upload_status} />
              </div>
            </div>
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Evidencia</div>
              <div>{doc.evidence || "—"}</div>
            </div>
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Factura</div>
              {doc.invoice_id ? (
                <Link href={`/facturas/${doc.invoice_id}`} className="text-[#033CA0]">
                  {formatInvoiceNumber(doc.invoice_number)}
                </Link>
              ) : (
                <span>—</span>
              )}
            </div>
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Persona</div>
              {doc.person_id ? (
                <Link href={`/personas/${doc.person_id}`} className="text-[#033CA0]">
                  {doc.full_name || doc.identity_number || "Ver persona"}
                </Link>
              ) : (
                <span>—</span>
              )}
            </div>
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Blob pathname</div>
              <code className="break-all text-xs text-slate-600">{doc.blob_pathname || "—"}</code>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
