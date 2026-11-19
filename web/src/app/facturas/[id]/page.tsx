import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { DocumentGallery } from "@/components/document-gallery";
import { EntityRow } from "@/components/entity-row";
import { PageHeader } from "@/components/page-header";
import { RelationSection } from "@/components/relation-section";
import { SectionNav } from "@/components/section-nav";
import { sql } from "@/lib/db";
import {
  formatAccount,
  formatDate,
  formatInvoiceNumber,
  formatMoney,
  formatSourceFileTitle,
  formatSourcePages,
  roleLabel,
} from "@/lib/format";

export const dynamic = "force-dynamic";

const AUTH_LIMIT = 20;

export default async function FacturaDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ file?: string }>;
}) {
  const { id } = await params;
  const { file: fileFilter = "" } = await searchParams;
  const db = sql();

  const [invoice] = await db`
    SELECT i.*, a.legal_name AS account, a.code AS account_code
    FROM avila.invoice i
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE i.id = ${id}::uuid
  `;
  if (!invoice) notFound();

  const people = await db`
    SELECT p.id, p.identity_number, p.full_name, ip.role::text AS role, ip.parentesco
    FROM avila.invoice_person ip
    JOIN avila.person p ON p.id = ip.person_id
    WHERE ip.invoice_id = ${id}::uuid
    ORDER BY CASE ip.role WHEN 'titular' THEN 0 WHEN 'beneficiario' THEN 1 ELSE 2 END, p.full_name
  `;

  const [authCountRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.authorization_line
    WHERE invoice_id = ${id}::uuid
  `;
  const authTotal = authCountRow?.n ?? 0;

  const authLines = await db`
    SELECT al.id, al.clave_rms, al.diagnosis, al.service_description, al.amount_bs, al.amount_usd,
           al.person_id, al.service_date, al.contratante, al.provider_name,
           p.full_name AS person_name, p.identity_number
    FROM avila.authorization_line al
    LEFT JOIN avila.person p ON p.id = al.person_id
    WHERE al.invoice_id = ${id}::uuid
    ORDER BY coalesce(al.service_date, al.created_at) DESC
    LIMIT ${AUTH_LIMIT}
  `;

  const files = await db`
    SELECT id, file_label, extension, pages, rule_id, backup_path
    FROM avila.source_file WHERE invoice_id = ${id}::uuid
    ORDER BY backup_path, created_at
  `;

  const docs = fileFilter
    ? await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, d.source_file_id
        FROM avila.document d
        WHERE d.invoice_id = ${id}::uuid
          AND d.source_file_id = ${fileFilter}::uuid
        ORDER BY d.page_index, d.document_type
      `
    : await db`
        SELECT d.id, d.page_index, d.document_type::text AS document_type,
               d.upload_status::text AS upload_status, d.source_file_id
        FROM avila.document d
        WHERE d.invoice_id = ${id}::uuid
        ORDER BY d.page_index, d.document_type
      `;

  const [docCountRow] = await db`
    SELECT count(*)::int AS n FROM avila.document WHERE invoice_id = ${id}::uuid
  `;
  const docTotal = docCountRow?.n ?? 0;

  const activeFile = files.find((f) => f.id === fileFilter);
  const relatedTotal = people.length + authTotal + files.length + docTotal;

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

      {relatedTotal > 8 ? (
        <SectionNav
          items={[
            { id: "resumen", label: "Resumen", count: 1 },
            { id: "personas", label: "Personas", count: people.length },
            { id: "autorizaciones", label: "Autorizaciones", count: authTotal },
            { id: "archivos", label: "Archivos", count: files.length },
            { id: "paginas", label: "Páginas", count: docTotal },
          ]}
        />
      ) : null}

      <Card id="resumen" className="scroll-mt-24 rounded-3xl border-border shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-medium">Resumen</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Cuenta</div>
            <div>
              {invoice.account_code ? (
                <Link
                  href={`/facturas?account=${invoice.account_code}`}
                  className="text-brand"
                >
                  {formatAccount(invoice.account)}
                </Link>
              ) : (
                formatAccount(invoice.account)
              )}
            </div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Control</div>
            <div>{invoice.control_number || "—"}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Emisión</div>
            <div>{formatDate(invoice.issue_date)}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Periodo</div>
            <div>
              {invoice.month || "—"} {invoice.year || ""}
            </div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Lote</div>
            <div>{invoice.lote || "—"}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Flujo</div>
            <div>{invoice.workflow || "—"}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Canal</div>
            <div>{invoice.channel || "—"}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Grupo duplicado</div>
            <div className="break-all">{invoice.duplicate_group || "—"}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-muted-foreground uppercase">Rango</div>
            <div>{invoice.invoice_range || "—"}</div>
          </div>
        </CardContent>
      </Card>

      <RelationSection
        collapsible
        id="personas"
        title="Personas"
        count={people.length}
        emptyTitle="Sin personas vinculadas"
        emptyHint="Ningún titular o beneficiario resuelto aún para esta factura."
      >
        <div className="space-y-2">
          {people.map((p) => (
            <EntityRow
              key={p.id}
              href={`/personas/${p.id}`}
              title={p.full_name || p.identity_number || p.id.slice(0, 8)}
              badges={[roleLabel(p.role)]}
              meta={[p.identity_number, p.parentesco].filter(Boolean).join(" · ")}
            />
          ))}
        </div>
      </RelationSection>

      <RelationSection
        collapsible
        id="autorizaciones"
        title="Autorizaciones"
        count={authTotal}
        emptyTitle="Sin autorizaciones"
        emptyHint="No hay líneas de sábana o relación vinculadas a este número de factura."
        footer={
          authTotal > AUTH_LIMIT ? (
            <p className="pt-2 text-xs text-muted-foreground">
              Mostrando {authLines.length} de {authTotal}
              {authTotal > authLines.length
                ? ` · y ${authTotal - authLines.length} más`
                : ""}
            </p>
          ) : null
        }
      >
        <div className="space-y-2">
          {authLines.map((line) => (
            <div
              key={line.id}
              className="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">{line.clave_rms || "Sin clave"}</span>
                <span className="text-muted-foreground">{formatDate(line.service_date)}</span>
              </div>
              <div className="mt-1 text-muted-foreground">
                {line.diagnosis || line.service_description || "Sin diagnóstico"}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                <span>{line.contratante || line.provider_name || "—"}</span>
                <span>BS {formatMoney(line.amount_bs)}</span>
                <span>USD {formatMoney(line.amount_usd)}</span>
                {line.person_id ? (
                  <Link href={`/personas/${line.person_id}`} className="text-brand">
                    {line.person_name || line.identity_number || "Ver persona"}
                  </Link>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </RelationSection>

      <RelationSection
        collapsible
        id="archivos"
        title="Archivos fuente"
        count={files.length}
        emptyTitle="Sin archivos fuente"
        emptyHint="Ningún paquete o anexo materializado para esta factura."
      >
        <div className="space-y-2">
          {files.map((f) => (
            <EntityRow
              key={f.id}
              href={`/facturas/${id}?file=${f.id}#paginas`}
              title={formatSourceFileTitle(f.backup_path, f.file_label, f.extension)}
              meta={[f.rule_id || f.file_label, fileFilter === f.id ? "Filtro activo" : null]
                .filter(Boolean)
                .join(" · ")}
              trailing={formatSourcePages(f.pages)}
            />
          ))}
        </div>
      </RelationSection>

      <RelationSection
        collapsible
        id="paginas"
        title="Páginas del paquete"
        count={fileFilter ? docs.length : docTotal}
        emptyTitle="Sin páginas en este paquete"
        emptyHint="Ejecuta la carga de documentos para materializar páginas en Blob."
        moreHref={fileFilter ? `/facturas/${id}#paginas` : undefined}
        moreLabel="Ver todas las páginas"
        footer={
          activeFile ? (
            <p className="pt-2 text-xs text-muted-foreground">
              Filtrado por archivo:{" "}
              {formatSourceFileTitle(
                activeFile.backup_path,
                activeFile.file_label,
                activeFile.extension,
              )}
            </p>
          ) : null
        }
      >
        <DocumentGallery
          blocks={[
            {
              id: "paginas",
              docs: docs.map((d) => ({
                id: d.id,
                documentType: d.document_type,
                pageIndex: d.page_index,
                uploadStatus: d.upload_status,
              })),
            },
          ]}
        />
      </RelationSection>
    </div>
  );
}
