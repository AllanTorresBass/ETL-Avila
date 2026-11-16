import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { DocumentTypeGroup } from "@/components/document-type-group";
import { EntityRow } from "@/components/entity-row";
import { PageHeader } from "@/components/page-header";
import { RelationSection } from "@/components/relation-section";
import { SectionNav } from "@/components/section-nav";
import { IDENTITY_TYPE_LABELS, sql } from "@/lib/db";
import {
  formatAccount,
  formatDate,
  formatInvoiceNumber,
  formatMoney,
  roleLabel,
} from "@/lib/format";

export const dynamic = "force-dynamic";

const AUTH_PAGE_SIZE = 20;

export default async function PersonaDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ authPage?: string }>;
}) {
  const { id } = await params;
  const { authPage: authPageRaw } = await searchParams;
  const db = sql();

  const [person] = await db`
    SELECT id, identity_type::text AS identity_type, identity_number, full_name,
           birth_date, phone, address, notes
    FROM avila.person WHERE id = ${id}::uuid
  `;
  if (!person) notFound();

  const [authCountRow] = await db`
    SELECT count(*)::int AS n
    FROM avila.authorization_line
    WHERE person_id = ${id}::uuid
  `;
  const authTotal = authCountRow?.n ?? 0;
  const authPageMax = Math.max(1, Math.ceil(authTotal / AUTH_PAGE_SIZE));
  const authPage = Math.min(
    authPageMax,
    Math.max(1, Number.parseInt(authPageRaw || "1", 10) || 1),
  );
  const authOffset = (authPage - 1) * AUTH_PAGE_SIZE;

  const invoices = await db`
    SELECT i.id, i.invoice_number, ip.role::text AS role, ip.parentesco,
           a.legal_name AS account
    FROM avila.invoice_person ip
    JOIN avila.invoice i ON i.id = ip.invoice_id
    LEFT JOIN avila.account a ON a.id = i.account_id
    WHERE ip.person_id = ${id}::uuid
    ORDER BY i.invoice_number
  `;

  const sourceFilesPrimary = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.invoice_id, i.invoice_number
    FROM avila.source_file sf
    JOIN avila.invoice i ON i.id = sf.invoice_id
    WHERE sf.invoice_id IN (
      SELECT invoice_id FROM avila.invoice_person WHERE person_id = ${id}::uuid
    )
    ORDER BY sf.id, i.invoice_number, sf.file_label
  `;

  const sourceFilesFallback = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.invoice_id, i.invoice_number
    FROM avila.document d
    JOIN avila.source_file sf ON sf.id = d.source_file_id
    LEFT JOIN avila.invoice i ON i.id = sf.invoice_id
    WHERE d.person_id = ${id}::uuid
      AND (
        sf.invoice_id IS NULL
        OR NOT EXISTS (
          SELECT 1 FROM avila.invoice_person ip
          WHERE ip.person_id = ${id}::uuid AND ip.invoice_id = sf.invoice_id
        )
      )
    ORDER BY sf.id, sf.file_label
  `;

  const sourceFileMap = new Map<string, (typeof sourceFilesPrimary)[number]>();
  for (const f of [...sourceFilesPrimary, ...sourceFilesFallback]) {
    sourceFileMap.set(f.id, f);
  }
  const sourceFiles = [...sourceFileMap.values()].sort((a, b) => {
    const an = a.invoice_number || "";
    const bn = b.invoice_number || "";
    if (an !== bn) return an.localeCompare(bn);
    return (a.file_label || "").localeCompare(b.file_label || "");
  });

  const lines = await db`
    SELECT id, clave_rms, contratante, service_date, request_date, diagnosis,
           service_description, provider_name, amount_bs, amount_usd,
           coverage_amount, authorized_amount, invoice_id
    FROM avila.authorization_line
    WHERE person_id = ${id}::uuid
    ORDER BY coalesce(service_date, request_date) DESC NULLS LAST, created_at DESC
    LIMIT ${AUTH_PAGE_SIZE} OFFSET ${authOffset}
  `;

  const identityDocs = await db`
    SELECT id, page_index, document_type::text AS document_type,
           upload_status::text AS upload_status
    FROM avila.document
    WHERE person_id = ${id}::uuid
    ORDER BY page_index, document_type
  `;

  const expedienteDocs = await db`
    SELECT d.id, d.page_index, d.document_type::text AS document_type,
           d.upload_status::text AS upload_status, d.invoice_id, i.invoice_number
    FROM avila.document d
    JOIN avila.invoice i ON i.id = d.invoice_id
    WHERE d.invoice_id IN (
      SELECT invoice_id FROM avila.invoice_person WHERE person_id = ${id}::uuid
    )
    AND (d.person_id IS DISTINCT FROM ${id}::uuid)
    ORDER BY i.invoice_number, d.page_index, d.document_type
  `;

  const identityType =
    IDENTITY_TYPE_LABELS[person.identity_type] || person.identity_type;
  const identityLine = `${identityType}: ${person.identity_number || "—"}`;

  const relatedTotal =
    invoices.length +
    sourceFiles.length +
    authTotal +
    identityDocs.length +
    expedienteDocs.length;

  const expedienteByInvoice = new Map<
    string,
    { invoiceId: string; invoiceNumber: string; docs: typeof expedienteDocs }
  >();
  for (const doc of expedienteDocs) {
    const key = doc.invoice_id || "none";
    const existing = expedienteByInvoice.get(key);
    if (existing) {
      existing.docs.push(doc);
    } else {
      expedienteByInvoice.set(key, {
        invoiceId: doc.invoice_id,
        invoiceNumber: doc.invoice_number,
        docs: [doc],
      });
    }
  }

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
        description={identityLine}
      />

      {relatedTotal > 8 ? (
        <SectionNav
          items={[
            { id: "facturas", label: "Facturas", count: invoices.length },
            { id: "archivos", label: "Archivos", count: sourceFiles.length },
            { id: "autorizaciones", label: "Autorizaciones", count: authTotal },
            { id: "identidad", label: "Identidad", count: identityDocs.length },
            { id: "expediente", label: "Expediente", count: expedienteDocs.length },
          ]}
        />
      ) : null}

      <Card className="rounded-3xl border-slate-100 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-medium">Identidad y contacto</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <div className="text-xs tracking-wider text-slate-400 uppercase">Identidad</div>
            <div>{identityLine}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-slate-400 uppercase">Nacimiento</div>
            <div>{formatDate(person.birth_date)}</div>
          </div>
          <div>
            <div className="text-xs tracking-wider text-slate-400 uppercase">Teléfono</div>
            <div>{person.phone || "—"}</div>
          </div>
          <div className="sm:col-span-2">
            <div className="text-xs tracking-wider text-slate-400 uppercase">Dirección</div>
            <div>{person.address || "—"}</div>
          </div>
          {person.notes ? (
            <div className="sm:col-span-2">
              <div className="text-xs tracking-wider text-slate-400 uppercase">Notas</div>
              <div>{person.notes}</div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <RelationSection
        id="facturas"
        title="Facturas"
        count={invoices.length}
        emptyTitle="Sin facturas vinculadas"
        emptyHint="Esta persona aún no aparece en invoice_person. Revisa autorizaciones o carga más paquetes."
      >
        <div className="space-y-2">
          {invoices.map((inv) => (
            <EntityRow
              key={`${inv.id}-${inv.role}`}
              href={`/facturas/${inv.id}`}
              title={formatInvoiceNumber(inv.invoice_number)}
              badges={[roleLabel(inv.role)]}
              meta={[inv.parentesco, formatAccount(inv.account)].filter(Boolean).join(" · ")}
            />
          ))}
        </div>
      </RelationSection>

      <RelationSection
        id="archivos"
        title="Archivos fuente"
        count={sourceFiles.length}
        emptyTitle="Sin archivos fuente"
        emptyHint="Los archivos se vinculan por factura. Cuando haya facturas cargadas, los paquetes aparecerán aquí."
      >
        <div className="space-y-2">
          {sourceFiles.map((f) => (
            <EntityRow
              key={f.id}
              href={
                f.invoice_id
                  ? `/facturas/${f.invoice_id}?file=${f.id}#paginas`
                  : undefined
              }
              title={`${f.file_label}${f.extension ? ` ${f.extension}` : ""}`}
              meta={
                f.invoice_number
                  ? formatInvoiceNumber(f.invoice_number)
                  : "Sin factura vinculada"
              }
              trailing={`${f.pages ?? "?"} pág`}
            />
          ))}
        </div>
      </RelationSection>

      <RelationSection
        id="autorizaciones"
        title="Autorizaciones"
        count={authTotal}
        emptyTitle="Sin autorizaciones"
        emptyHint="Sin líneas de sábana, relación o cintillo vinculadas a esta persona."
        footer={
          authTotal > AUTH_PAGE_SIZE ? (
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-slate-500">
              <span>
                Mostrando {lines.length} de {authTotal}
                {authTotal > lines.length + authOffset
                  ? ` · y ${authTotal - authOffset - lines.length} más`
                  : ""}
              </span>
              <div className="flex gap-2">
                {authPage > 1 ? (
                  <Link
                    href={`/personas/${id}?authPage=${authPage - 1}#autorizaciones`}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 font-medium text-[#033CA0]"
                  >
                    Anterior
                  </Link>
                ) : null}
                {authOffset + lines.length < authTotal ? (
                  <Link
                    href={`/personas/${id}?authPage=${authPage + 1}#autorizaciones`}
                    className="btn-green-gradient rounded-full px-3 py-1.5 font-medium text-white"
                  >
                    Siguiente
                  </Link>
                ) : null}
              </div>
            </div>
          ) : null
        }
      >
        <div className="space-y-2">
          {lines.map((line) => (
            <div
              key={line.id}
              className="rounded-2xl border border-slate-100 bg-slate-50/60 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">{line.clave_rms || "Sin clave"}</span>
                <span className="text-slate-500">
                  {formatDate(line.service_date || line.request_date)}
                </span>
              </div>
              <div className="mt-1 text-slate-600">
                {line.diagnosis || line.service_description || "Sin diagnóstico"}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
                <span>{line.contratante || line.provider_name || "—"}</span>
                <span>BS {formatMoney(line.amount_bs)}</span>
                <span>USD {formatMoney(line.amount_usd)}</span>
                {line.invoice_id ? (
                  <Link href={`/facturas/${line.invoice_id}`} className="text-[#033CA0]">
                    Ver factura
                  </Link>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </RelationSection>

      <RelationSection
        id="identidad"
        title="Documentos de identidad"
        count={identityDocs.length}
        emptyTitle="Sin documentos de identidad"
        emptyHint="Solo páginas con cédula o pasaporte vinculadas por person_id aparecen aquí."
      >
        <DocumentTypeGroup
          docs={identityDocs.map((d) => ({
            id: d.id,
            document_type: d.document_type,
            page_index: d.page_index,
            upload_status: d.upload_status,
          }))}
        />
      </RelationSection>

      <RelationSection
        id="expediente"
        title="Documentos del expediente"
        count={expedienteDocs.length}
        emptyTitle="Sin documentos del expediente"
        emptyHint="Páginas de facturas vinculadas (egresos, informes, fiscal) aparecerán cuando existan paquetes cargados."
      >
        <div className="space-y-6">
          {[...expedienteByInvoice.values()].map((group) => (
            <div key={group.invoiceId} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-medium text-[#0A2A6B]">
                  {formatInvoiceNumber(group.invoiceNumber)}
                </h3>
                <Link
                  href={`/facturas/${group.invoiceId}`}
                  className="text-xs font-medium text-[#033CA0]"
                >
                  Ver factura
                </Link>
              </div>
              <DocumentTypeGroup
                docs={group.docs.map((d) => ({
                  id: d.id,
                  document_type: d.document_type,
                  page_index: d.page_index,
                  upload_status: d.upload_status,
                  subtitle: formatInvoiceNumber(d.invoice_number),
                }))}
              />
            </div>
          ))}
        </div>
      </RelationSection>
    </div>
  );
}
