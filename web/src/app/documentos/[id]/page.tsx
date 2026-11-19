import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { EntityRow } from "@/components/entity-row";
import { PageHeader } from "@/components/page-header";
import { RelationSection } from "@/components/relation-section";
import { UploadStatusBadge } from "@/components/upload-status-badge";
import { DocumentPreview } from "@/components/document-preview";
import { DOCUMENT_TYPE_LABELS, ROLE_LABELS, sql } from "@/lib/db";
import { formatInvoiceNumber, formatSourceFileTitle } from "@/lib/format";

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
           d.invoice_id, d.person_id, d.source_file_id,
           i.invoice_number,
           p.identity_number, p.full_name,
           sf.file_label, sf.extension, sf.pages AS source_pages, sf.rule_id,
           sf.backup_path
    FROM avila.document d
    LEFT JOIN avila.invoice i ON i.id = d.invoice_id
    LEFT JOIN avila.person p ON p.id = d.person_id
    LEFT JOIN avila.source_file sf ON sf.id = d.source_file_id
    WHERE d.id = ${id}::uuid
  `;
  if (!doc) notFound();

  const siblings = doc.source_file_id
    ? await db`
        SELECT id, page_index, document_type::text AS document_type,
               upload_status::text AS upload_status
        FROM avila.document
        WHERE source_file_id = ${doc.source_file_id}::uuid
        ORDER BY page_index
      `
    : [];

  const invoicePeople = doc.invoice_id
    ? await db`
        SELECT p.id, p.full_name, p.identity_number, ip.role::text AS role
        FROM avila.invoice_person ip
        JOIN avila.person p ON p.id = ip.person_id
        WHERE ip.invoice_id = ${doc.invoice_id}::uuid
        ORDER BY CASE ip.role
          WHEN 'titular' THEN 0
          WHEN 'beneficiario' THEN 1
          ELSE 2
        END, p.full_name
      `
    : [];

  const currentIdx = siblings.findIndex((s) => s.id === doc.id);
  const prev = currentIdx > 0 ? siblings[currentIdx - 1] : null;
  const next =
    currentIdx >= 0 && currentIdx < siblings.length - 1 ? siblings[currentIdx + 1] : null;

  const typeLabel = DOCUMENT_TYPE_LABELS[doc.document_type] || doc.document_type;
  const canPreview = doc.upload_status === "uploaded" && Boolean(doc.blob_url || doc.blob_pathname);
  const titular = invoicePeople.find((p) => p.role === "titular") || null;
  const profileTarget =
    (doc.person_id
      ? { id: doc.person_id as string, name: doc.full_name || doc.identity_number || "persona" }
      : null) ||
    (titular
      ? {
          id: titular.id as string,
          name: titular.full_name || titular.identity_number || "titular",
        }
      : null);

  const crumbItems = [
    { href: "/", label: "Inicio" },
    { href: "/documentos", label: "Documentos" },
    ...(doc.invoice_id
      ? [
          {
            href: `/facturas/${doc.invoice_id}`,
            label: formatInvoiceNumber(doc.invoice_number),
          },
        ]
      : []),
    { label: typeLabel },
  ];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={crumbItems} />
      <PageHeader
        eyebrow="Documento"
        title={typeLabel}
        description={`Página ${doc.page_index}${doc.invoice_number ? ` · ${formatInvoiceNumber(doc.invoice_number)}` : ""}`}
      />

      <div className="flex flex-wrap gap-2">
        {prev ? (
          <Link
            href={`/documentos/${prev.id}`}
            className="rounded-full border border-border bg-card px-4 py-2 text-xs font-medium text-brand"
          >
            ← Página {prev.page_index}
          </Link>
        ) : null}
        {next ? (
          <Link
            href={`/documentos/${next.id}`}
            className="rounded-full border border-border bg-card px-4 py-2 text-xs font-medium text-brand"
          >
            Página {next.page_index} →
          </Link>
        ) : null}
        {profileTarget ? (
          <Link
            href={`/personas/${profileTarget.id}`}
            className="btn-green-gradient rounded-full px-4 py-2 text-xs font-medium text-white"
          >
            Ver perfil · {profileTarget.name}
          </Link>
        ) : null}
        {titular && profileTarget && titular.id !== profileTarget.id ? (
          <Link
            href={`/personas/${titular.id}`}
            className="rounded-full border border-border bg-card px-4 py-2 text-xs font-medium text-brand"
          >
            Titular · {titular.full_name || titular.identity_number}
          </Link>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden rounded-3xl border-border shadow-sm">
          <CardContent className="p-0">
            {canPreview ? (
              <DocumentPreview src={`/api/blob/${doc.id}`} alt={typeLabel} />
            ) : (
              <div className="flex h-64 flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
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
        <Card className="rounded-3xl border-border shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg font-medium">Detalle</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Tipo</div>
              <Badge
                className={`mt-1 rounded-full ${
                  doc.document_type === "ilegible" ? "bg-warning-soft text-warning" : ""
                }`}
              >
                {typeLabel}
              </Badge>
            </div>
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Página</div>
              <div>{doc.page_index}</div>
            </div>
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Estado Blob</div>
              <div className="mt-1">
                <UploadStatusBadge status={doc.upload_status} />
              </div>
            </div>
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Evidencia</div>
              <div>{doc.evidence || "—"}</div>
            </div>
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Factura</div>
              {doc.invoice_id ? (
                <Link href={`/facturas/${doc.invoice_id}`} className="text-brand">
                  {formatInvoiceNumber(doc.invoice_number)}
                </Link>
              ) : (
                <span>—</span>
              )}
            </div>
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">
                Persona en este documento
              </div>
              {doc.person_id ? (
                <Link href={`/personas/${doc.person_id}`} className="font-medium text-brand">
                  {doc.full_name || doc.identity_number || "Ver persona"}
                </Link>
              ) : titular ? (
                <Link href={`/personas/${titular.id}`} className="font-medium text-brand">
                  {titular.full_name || titular.identity_number}{" "}
                  <span className="font-normal text-muted-foreground">(titular del paquete)</span>
                </Link>
              ) : (
                <span className="text-muted-foreground">
                  Sin vínculo — revisa las personas de la factura
                </span>
              )}
            </div>
            {invoicePeople.length > 0 ? (
              <div>
                <div className="text-xs tracking-wider text-muted-foreground uppercase">
                  Personas del expediente
                </div>
                <ul className="mt-1 space-y-1">
                  {invoicePeople.map((person) => (
                    <li key={`${person.id}-${person.role}`}>
                      <Link
                        href={`/personas/${person.id}`}
                        className="text-brand hover:underline"
                      >
                        {ROLE_LABELS[person.role] || person.role}:{" "}
                        {person.full_name || person.identity_number || "Ver persona"}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Archivo fuente</div>
              {doc.source_file_id ? (
                doc.invoice_id ? (
                  <Link
                    href={`/facturas/${doc.invoice_id}?file=${doc.source_file_id}#paginas`}
                    className="text-brand"
                  >
                    {formatSourceFileTitle(doc.backup_path, doc.file_label, doc.extension)}
                    {doc.source_pages != null ? ` · ${doc.source_pages} pág` : ""}
                  </Link>
                ) : (
                  <span>
                    {formatSourceFileTitle(doc.backup_path, doc.file_label, doc.extension)}
                  </span>
                )
              ) : (
                <span>—</span>
              )}
            </div>
            {doc.rule_id ? (
              <div>
                <div className="text-xs tracking-wider text-muted-foreground uppercase">Regla</div>
                <div>{doc.rule_id}</div>
              </div>
            ) : null}
            <div>
              <div className="text-xs tracking-wider text-muted-foreground uppercase">Blob pathname</div>
              <code className="break-all text-xs text-muted-foreground">{doc.blob_pathname || "—"}</code>
            </div>
          </CardContent>
        </Card>
      </div>

      {siblings.length > 1 ? (
        <RelationSection
          id="hermanas"
          title="Páginas del mismo archivo"
          count={siblings.length}
          emptyTitle="Sin páginas hermanas"
          emptyHint="Este documento es la única página del archivo fuente."
        >
          <div className="space-y-2">
            {siblings.map((s) => (
              <EntityRow
                key={s.id}
                href={s.id === doc.id ? undefined : `/documentos/${s.id}`}
                title={`Página ${s.page_index}`}
                badges={[
                  DOCUMENT_TYPE_LABELS[s.document_type] || s.document_type,
                  ...(s.id === doc.id ? ["Actual"] : []),
                ]}
                meta={s.upload_status || undefined}
              />
            ))}
          </div>
        </RelationSection>
      ) : null}
    </div>
  );
}
