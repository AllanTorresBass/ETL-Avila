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

function roleLabel(role: string) {
  if (role === "titular") return "Titular";
  if (role === "beneficiario") return "Beneficiario";
  return "Sin rol claro";
}

function formatDate(value: string | Date | null | undefined) {
  if (!value) return "—";
  const d = typeof value === "string" ? value.slice(0, 10) : value.toISOString().slice(0, 10);
  return d;
}

function formatMoney(value: string | number | null | undefined) {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("es-VE", { maximumFractionDigits: 2 });
}

export default async function PersonaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const db = sql();
  const [person] = await db`
    SELECT id, identity_type::text AS identity_type, identity_number, full_name,
           birth_date, phone, address, notes
    FROM avila.person WHERE id = ${id}::uuid
  `;
  if (!person) notFound();

  const invoices = await db`
    SELECT i.id, i.invoice_number, ip.role::text AS role, ip.parentesco,
           a.legal_name AS account
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
  const lines = await db`
    SELECT id, clave_rms, contratante, service_date, request_date, diagnosis,
           service_description, provider_name, amount_bs, amount_usd,
           coverage_amount, authorized_amount, invoice_id
    FROM avila.authorization_line
    WHERE person_id = ${id}::uuid
    ORDER BY coalesce(service_date, request_date) DESC NULLS LAST, created_at DESC
    LIMIT 50
  `;

  const identityLine = `${person.identity_type}: ${person.identity_number || "—"}`;

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

      <Card className="rounded-3xl border-slate-100 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-medium">Datos de contacto</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
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
                key={`${inv.id}-${inv.role}`}
                href={`/facturas/${inv.id}`}
                className="flex justify-between text-sm hover:text-[#033CA0]"
              >
                <span>{formatInvoiceNumber(inv.invoice_number)}</span>
                <span className="text-slate-500">
                  {roleLabel(inv.role)}
                  {inv.parentesco ? ` · ${inv.parentesco}` : ""} · {formatAccount(inv.account)}
                </span>
              </Link>
            ))
          )}
        </CardContent>
      </Card>

      <Card className="rounded-3xl border-slate-100 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-medium">Autorizaciones / líneas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {lines.length === 0 ? (
            <p className="text-sm text-slate-500">
              Sin líneas de sábana/relación/cintillo vinculadas a esta persona.
            </p>
          ) : (
            lines.map((line) => (
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
