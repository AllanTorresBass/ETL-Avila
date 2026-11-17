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
import { FIELD_LABELS, SOURCE_KIND_LABELS } from "@/lib/review";
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

const AUTH_PAGE_SIZE = 20;
const HISTORY_LIMIT = 50;

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

  // People linked as beneficiario on invoices where this person is titular.
  const beneficiaries = await db`
    SELECT b.id, b.full_name, b.identity_number,
           count(DISTINCT i.id)::int AS invoice_count,
           max(bip.parentesco) AS parentesco
    FROM avila.invoice_person tip
    JOIN avila.invoice i ON i.id = tip.invoice_id
    JOIN avila.invoice_person bip
      ON bip.invoice_id = tip.invoice_id
     AND bip.role = 'beneficiario'
     AND bip.person_id <> tip.person_id
    JOIN avila.person b ON b.id = bip.person_id
    WHERE tip.person_id = ${id}::uuid
      AND tip.role = 'titular'
    GROUP BY b.id, b.full_name, b.identity_number
    ORDER BY lower(coalesce(b.full_name, '')), b.identity_number
  `;

  // Titulares on invoices where this person is beneficiario (critical navigation).
  const titulares = await db`
    SELECT t.id, t.full_name, t.identity_number, t.phone,
           count(DISTINCT i.id)::int AS invoice_count,
           max(bip.parentesco) AS parentesco
    FROM avila.invoice_person bip
    JOIN avila.invoice i ON i.id = bip.invoice_id
    JOIN avila.invoice_person tip
      ON tip.invoice_id = bip.invoice_id
     AND tip.role = 'titular'
     AND tip.person_id <> bip.person_id
    JOIN avila.person t ON t.id = tip.person_id
    WHERE bip.person_id = ${id}::uuid
      AND bip.role = 'beneficiario'
    GROUP BY t.id, t.full_name, t.identity_number, t.phone
    ORDER BY lower(coalesce(t.full_name, '')), t.identity_number
  `;
  const primaryTitular = titulares[0] ?? null;

  const sourceFilesPrimary = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.backup_path,
           sf.invoice_id, i.invoice_number, sf.rule_id
    FROM avila.source_file sf
    JOIN avila.invoice i ON i.id = sf.invoice_id
    WHERE sf.invoice_id IN (
      SELECT invoice_id FROM avila.invoice_person WHERE person_id = ${id}::uuid
    )
    ORDER BY sf.id, i.invoice_number, sf.file_label
  `;

  const sourceFilesFallback = await db`
    SELECT DISTINCT ON (sf.id)
           sf.id, sf.file_label, sf.extension, sf.pages, sf.backup_path,
           sf.invoice_id, i.invoice_number, sf.rule_id
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
    const ap = a.backup_path || a.file_label || "";
    const bp = b.backup_path || b.file_label || "";
    return ap.localeCompare(bp);
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

  const history = await db`
    SELECT fp.id, fp.entity, fp.field, fp.source_kind, fp.source_ref, fp.rule_id,
           fp.confidence, fp.reason, fp.created_at, r.script
    FROM avila.field_provenance fp
    LEFT JOIN avila.etl_run r ON r.id = fp.run_id
    WHERE (fp.entity = 'person' AND fp.entity_id = ${id})
       OR (fp.entity = 'invoice_person' AND fp.entity_id = ANY(${invoices.map((i) => `${i.id}:${id}`)}))
    ORDER BY fp.created_at DESC, fp.id DESC
    LIMIT ${HISTORY_LIMIT}
  `;

  const identityType =
    IDENTITY_TYPE_LABELS[person.identity_type] || person.identity_type;
  const identityLine = `${identityType}: ${person.identity_number || "—"}`;

  const relatedTotal =
    invoices.length +
    titulares.length +
    beneficiaries.length +
    sourceFiles.length +
    authTotal +
    identityDocs.length +
    expedienteDocs.length +
    history.length;

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

      {primaryTitular ? (
        <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-[#0A2A6B]/15 bg-white px-5 py-4 shadow-sm">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium tracking-wider text-[#5BB2F5] uppercase">
              Titular del expediente
            </div>
            <div className="mt-0.5 text-base font-medium text-[#0A2A6B]">
              {primaryTitular.full_name || primaryTitular.identity_number || "Titular"}
            </div>
            <div className="text-xs text-slate-500">
              {[
                primaryTitular.identity_number
                  ? `Cédula ${primaryTitular.identity_number}`
                  : null,
                primaryTitular.parentesco
                  ? `Parentesco: ${primaryTitular.parentesco}`
                  : null,
                `${primaryTitular.invoice_count} factura${
                  primaryTitular.invoice_count === 1 ? "" : "s"
                }`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </div>
          <Link
            href={`/personas/${primaryTitular.id}`}
            className="btn-green-gradient rounded-full px-5 py-2.5 text-xs font-medium text-white"
          >
            Ver titular
          </Link>
        </div>
      ) : null}

      {relatedTotal > 8 ? (
        <SectionNav
          items={[
            ...(titulares.length > 0
              ? [{ id: "titulares", label: "Titulares", count: titulares.length }]
              : []),
            { id: "facturas", label: "Facturas", count: invoices.length },
            ...(beneficiaries.length > 0
              ? [{ id: "beneficiarios", label: "Beneficiarios", count: beneficiaries.length }]
              : []),
            { id: "archivos", label: "Archivos", count: sourceFiles.length },
            { id: "autorizaciones", label: "Autorizaciones", count: authTotal },
            { id: "identidad", label: "Identidad", count: identityDocs.length },
            { id: "expediente", label: "Expediente", count: expedienteDocs.length },
            { id: "historial", label: "Historial", count: history.length },
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
          {primaryTitular ? (
            <div>
              <div className="text-xs tracking-wider text-slate-400 uppercase">Titular</div>
              <Link
                href={`/personas/${primaryTitular.id}`}
                className="font-medium text-[#033CA0] hover:underline"
              >
                {primaryTitular.full_name || primaryTitular.identity_number}
                {primaryTitular.identity_number
                  ? ` · V-${primaryTitular.identity_number}`
                  : ""}
              </Link>
            </div>
          ) : null}
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

      {titulares.length > 0 ? (
        <RelationSection
          id="titulares"
          title="Titulares"
          count={titulares.length}
          emptyTitle="Sin titular vinculado"
          emptyHint="No hay titular en las facturas donde esta persona es beneficiario."
        >
          <div className="space-y-2">
            {titulares.map((t) => (
              <EntityRow
                key={t.id}
                href={`/personas/${t.id}`}
                title={t.full_name || t.identity_number || "Sin nombre"}
                badges={[
                  "Titular",
                  ...(t.parentesco ? [String(t.parentesco)] : []),
                ]}
                meta={[
                  t.identity_number ? `Cédula ${t.identity_number}` : null,
                  t.phone ? `Tel. ${t.phone}` : null,
                  `${t.invoice_count} factura${t.invoice_count === 1 ? "" : "s"}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
            ))}
          </div>
        </RelationSection>
      ) : null}

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

      {beneficiaries.length > 0 ? (
        <RelationSection
          id="beneficiarios"
          title="Beneficiarios"
          count={beneficiaries.length}
          emptyTitle="Sin beneficiarios"
          emptyHint="No hay otros personas con rol beneficiario en las facturas donde esta persona es titular."
        >
          <div className="space-y-2">
            {beneficiaries.map((b) => (
              <EntityRow
                key={b.id}
                href={`/personas/${b.id}`}
                title={b.full_name || b.identity_number || "Sin nombre"}
                badges={[
                  "Beneficiario",
                  ...(b.parentesco ? [String(b.parentesco)] : []),
                ]}
                meta={[
                  b.identity_number ? `Cédula ${b.identity_number}` : null,
                  `${b.invoice_count} factura${b.invoice_count === 1 ? "" : "s"}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              />
            ))}
          </div>
        </RelationSection>
      ) : null}

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
              title={formatSourceFileTitle(f.backup_path, f.file_label, f.extension)}
              meta={[
                f.invoice_number
                  ? formatInvoiceNumber(f.invoice_number)
                  : "Sin factura vinculada",
                f.rule_id || null,
              ]
                .filter(Boolean)
                .join(" · ")}
              trailing={formatSourcePages(f.pages)}
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

      <RelationSection
        id="historial"
        title="Historial"
        count={history.length}
        emptyTitle="Sin historial"
        emptyHint="Los cambios hechos por el ETL o por la revisión se registran aquí con su fuente y regla."
      >
        <ol className="space-y-2">
          {history.map((h) => (
            <li
              key={h.id}
              className="rounded-2xl border border-slate-100 bg-slate-50/60 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-medium text-[#0A2A6B]">
                  {FIELD_LABELS[h.field] || h.field}
                </span>
                <span className="text-xs text-slate-500">{formatDate(h.created_at)}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                <span className="rounded-full bg-[#033CA0]/10 px-2 py-0.5 text-[#033CA0]">
                  {SOURCE_KIND_LABELS[h.source_kind] || h.source_kind}
                </span>
                <span>Regla {h.rule_id}</span>
                {h.confidence != null ? (
                  <span>Confianza {Number(h.confidence).toFixed(2)}</span>
                ) : null}
                {h.script ? <span>{h.script}</span> : null}
              </div>
              {h.source_ref || h.reason ? (
                <div className="mt-1 break-all text-xs text-slate-400">
                  {[h.source_ref, h.reason].filter(Boolean).join(" · ")}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </RelationSection>
    </div>
  );
}
