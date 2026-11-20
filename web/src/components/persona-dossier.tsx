import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { DocumentGallery } from "@/components/document-gallery";
import { EntityRow } from "@/components/entity-row";
import { EntityTabs, type EntityTabPanel } from "@/components/entity-tabs";
import { Pagination } from "@/components/pagination";
import { CONTACT_GAP_COPY, contactGapCode } from "@/lib/contact-gap";
import {
  PERSONA_AUTH_PAGE_SIZE,
  PERSONA_HISTORY_LIMIT,
  type PersonaDetail,
  type PersonaTabId,
} from "@/lib/persona-data";
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

const n = (v: number) => v.toLocaleString("es-VE");

function GapNote({
  gap,
  field,
}: {
  gap: unknown;
  field: "birth_date" | "phone" | "address";
}) {
  const code = contactGapCode(gap, field);
  const text = code ? CONTACT_GAP_COPY[code] : undefined;
  if (!text) return null;
  return <p className="mt-1 text-xs text-muted-foreground">{text}</p>;
}

function Chip({
  ok,
  label,
}: {
  ok: boolean;
  label: string;
}) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
        ok ? "bg-success-soft text-success" : "bg-warning-soft text-warning"
      }`}
    >
      {label}
    </span>
  );
}

/** Sticky summary strip always visible above dossier tabs. */
export function PersonaSummary({
  detail,
  personId,
}: {
  detail: PersonaDetail;
  personId: string;
}) {
  const { person, identityLine, incompleteName, roleCounts, primaryTitular, titulares, openReviews } =
    detail;
  const hasCi = Boolean(person.identity_number?.trim());
  const hasPhone = Boolean(person.phone?.trim()) && !contactGapCode(person.contact_gap, "phone");
  const hasBirth =
    Boolean(person.birth_date) && !contactGapCode(person.contact_gap, "birth_date");
  const hasAddress =
    Boolean(person.address?.trim()) && !contactGapCode(person.contact_gap, "address");

  const roleBadges: { label: string; className: string }[] = [];
  for (const role of ["titular", "beneficiario"] as const) {
    const count = roleCounts.get(role);
    if (!count) continue;
    roleBadges.push({
      label: `${roleLabel(role)} · ${count} factura${count === 1 ? "" : "s"}`,
      className:
        role === "titular"
          ? "rounded-full bg-hero px-3 py-1 text-xs font-medium text-white"
          : "rounded-full bg-brand/10 px-3 py-1 text-xs font-medium text-brand",
    });
  }
  if (roleBadges.length === 0) {
    roleBadges.push({
      label: roleLabel("unknown"),
      className: "rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground",
    });
  }
  if (incompleteName) {
    roleBadges.push({
      label: "Nombre incompleto",
      className: "rounded-full bg-warning-soft px-3 py-1 text-xs font-medium text-warning",
    });
  }

  return (
    <div className="space-y-4">
      <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
        <p className="text-xs font-medium tracking-wider text-info uppercase">Persona</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-3xl font-medium tracking-tight text-foreground">
            {person.full_name?.trim() || "Sin nombre"}
          </h1>
          {roleBadges.map((b) => (
            <span key={b.label} className={b.className}>
              {b.label}
            </span>
          ))}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{identityLine}</p>

        <div className="mt-4 flex flex-wrap gap-2" aria-label="Completitud">
          <Chip ok={hasCi} label={hasCi ? "Cédula" : "Sin cédula"} />
          <Chip ok={hasPhone} label={hasPhone ? "Teléfono" : "Sin teléfono"} />
          <Chip ok={hasBirth} label={hasBirth ? "Nacimiento" : "Sin nacimiento"} />
          <Chip ok={hasAddress} label={hasAddress ? "Dirección" : "Sin dirección"} />
        </div>

        <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs tracking-wider text-muted-foreground uppercase">Identidad</dt>
            <dd>{identityLine}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wider text-muted-foreground uppercase">Nacimiento</dt>
            <dd>{formatDate(person.birth_date)}</dd>
            <GapNote gap={person.contact_gap} field="birth_date" />
          </div>
          <div>
            <dt className="text-xs tracking-wider text-muted-foreground uppercase">Teléfono</dt>
            <dd>{person.phone || "—"}</dd>
            <GapNote gap={person.contact_gap} field="phone" />
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs tracking-wider text-muted-foreground uppercase">Dirección</dt>
            <dd>{person.address || "—"}</dd>
            <GapNote gap={person.contact_gap} field="address" />
          </div>
          {person.notes ? (
            <div className="sm:col-span-2">
              <dt className="text-xs tracking-wider text-muted-foreground uppercase">Notas</dt>
              <dd>{person.notes}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      {openReviews > 0 ? (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-3xl border border-warning/30 bg-warning-soft/60 px-5 py-4"
        >
          <AlertTriangle aria-hidden className="size-5 shrink-0 text-warning" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">
              {n(openReviews)} caso{openReviews === 1 ? "" : "s"} abierto
              {openReviews === 1 ? "" : "s"} en revisión
            </p>
            <p className="text-xs text-muted-foreground">
              Conflictos o decisiones pendientes que afectan a esta persona o sus facturas.
            </p>
          </div>
          <Link
            href="/revision"
            className="rounded-full border border-border bg-card px-4 py-2 text-xs font-medium text-brand shadow-sm hover:bg-muted"
          >
            Abrir revisión
          </Link>
        </div>
      ) : null}

      {primaryTitular ? (
        <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-border bg-card px-5 py-4 shadow-sm">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium tracking-wider text-info uppercase">
              Titular del expediente
            </div>
            <div className="mt-0.5 text-base font-medium text-foreground">
              {primaryTitular.full_name || primaryTitular.identity_number || "Titular"}
            </div>
            <div className="text-xs text-muted-foreground">
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
              {titulares.length > 1 ? (
                <>
                  {" · "}
                  <Link
                    href={`/personas/${personId}?tab=red`}
                    className="font-medium text-brand hover:underline"
                  >
                    +{titulares.length - 1} más
                  </Link>
                </>
              ) : null}
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
    </div>
  );
}

function EmptyHint({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-muted/40 px-4 py-6 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}

/** Tabbed dossier body for a persona profile. */
export function PersonaDossierTabs({
  detail,
  personId,
  defaultTab,
}: {
  detail: PersonaDetail;
  personId: string;
  defaultTab: PersonaTabId;
}) {
  const {
    invoices,
    facturaBlocks,
    expedienteByInvoice,
    identityDocs,
    authTotal,
    authPage,
    lines,
    titulares,
    beneficiaries,
    sourceFiles,
    history,
  } = detail;

  const panels: EntityTabPanel[] = [
    {
      id: "facturas",
      label: "Facturas",
      count: n(invoices.length),
      title: "Facturas",
      description: "Facturas vinculadas y páginas del expediente por factura.",
      body:
        invoices.length === 0 ? (
          <EmptyHint
            title="Sin facturas vinculadas"
            hint="Esta persona aún no aparece en invoice_person. Revisa autorizaciones o carga más paquetes."
          />
        ) : (
          <DocumentGallery
            blocks={[...facturaBlocks.values()].map((block) => ({
              id: block.id,
              title: block.title,
              href: block.href,
              meta: [block.roles.join(", "), block.parentesco, formatAccount(block.account)]
                .filter(Boolean)
                .join(" · "),
              docs: (expedienteByInvoice.get(block.id)?.docs ?? []).map((d) => ({
                id: d.id,
                documentType: d.document_type,
                pageIndex: d.page_index,
                uploadStatus: d.upload_status,
                subtitle: formatInvoiceNumber(d.invoice_number),
              })),
            }))}
          />
        ),
    },
    {
      id: "identidad",
      label: "Identidad",
      count: n(identityDocs.length),
      title: "Documentos de identidad",
      description: "Cédula, carnet u otros documentos vinculados por person_id.",
      body:
        identityDocs.length === 0 ? (
          <EmptyHint
            title="Sin documentos de identidad"
            hint="Solo páginas con cédula o pasaporte vinculadas por person_id aparecen aquí."
          />
        ) : (
          <DocumentGallery
            blocks={[
              {
                id: "identidad",
                docs: identityDocs.map((d) => ({
                  id: d.id,
                  documentType: d.document_type,
                  pageIndex: d.page_index,
                  uploadStatus: d.upload_status,
                })),
              },
            ]}
          />
        ),
    },
    {
      id: "autorizaciones",
      label: "Autorizaciones",
      count: n(authTotal),
      title: "Autorizaciones",
      description: "Líneas de sábana, relación o cintillo vinculadas a esta persona.",
      body:
        authTotal === 0 ? (
          <EmptyHint
            title="Sin autorizaciones"
            hint="Sin líneas de sábana, relación o cintillo vinculadas a esta persona."
          />
        ) : (
          <div className="space-y-3">
            <div className="space-y-2">
              {lines.map((line) => (
                <div
                  key={line.id}
                  className="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm"
                >
                  <div className="flex flex-wrap justify-between gap-2">
                    <span className="font-medium">{line.clave_rms || "Sin clave"}</span>
                    <span className="text-muted-foreground">
                      {formatDate(line.service_date || line.request_date)}
                    </span>
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    {line.diagnosis || line.service_description || "Sin diagnóstico"}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    <span>{line.contratante || line.provider_name || "—"}</span>
                    <span>BS {formatMoney(line.amount_bs)}</span>
                    <span>USD {formatMoney(line.amount_usd)}</span>
                    {line.invoice_id ? (
                      <Link href={`/facturas/${line.invoice_id}`} className="text-brand">
                        Ver factura
                      </Link>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
            <Pagination
              page={authPage}
              pageSize={PERSONA_AUTH_PAGE_SIZE}
              total={authTotal}
              shown={lines.length}
              basePath={`/personas/${personId}`}
              pageParam="authPage"
              searchParams={{ tab: "autorizaciones" }}
            />
          </div>
        ),
    },
  ];

  if (titulares.length > 0 || beneficiaries.length > 0) {
    panels.push({
      id: "red",
      label: "Red",
      count: n(titulares.length + beneficiaries.length),
      title: "Red familiar",
      description: "Titulares y beneficiarios vinculados por facturas compartidas.",
      body: (
        <div className="space-y-6">
          {titulares.length > 0 ? (
            <div>
              <h3 className="mb-3 text-sm font-medium text-foreground">
                Titulares ({n(titulares.length)})
              </h3>
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
            </div>
          ) : (
            <EmptyHint
              title="Sin titular vinculado"
              hint="No hay titular en las facturas donde esta persona es beneficiario."
            />
          )}
          {beneficiaries.length > 0 ? (
            <div>
              <h3 className="mb-3 text-sm font-medium text-foreground">
                Beneficiarios ({n(beneficiaries.length)})
              </h3>
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
            </div>
          ) : null}
        </div>
      ),
    });
  }

  panels.push(
    {
      id: "archivos",
      label: "Archivos",
      count: n(sourceFiles.length),
      title: "Archivos fuente",
      description: "Paquetes de origen vinculados por factura o por documentos de esta persona.",
      body:
        sourceFiles.length === 0 ? (
          <EmptyHint
            title="Sin archivos fuente"
            hint="Los archivos se vinculan por factura. Cuando haya facturas cargadas, los paquetes aparecerán aquí."
          />
        ) : (
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
        ),
    },
    {
      id: "historial",
      label: "Historial",
      count: n(history.length),
      title: "Historial",
      description: `Últimos ${PERSONA_HISTORY_LIMIT} cambios de procedencia (ETL o revisión).`,
      body:
        history.length === 0 ? (
          <EmptyHint
            title="Sin historial"
            hint="Los cambios hechos por el ETL o por la revisión se registran aquí con su fuente y regla."
          />
        ) : (
          <ol className="space-y-2">
            {history.map((h) => (
              <li
                key={h.id}
                className="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium text-foreground">
                    {FIELD_LABELS[h.field] || h.field}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDate(h.created_at)}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span className="rounded-full bg-brand/10 px-2 py-0.5 text-brand">
                    {SOURCE_KIND_LABELS[h.source_kind] || h.source_kind}
                  </span>
                  <span>Regla {h.rule_id}</span>
                  {h.confidence != null ? (
                    <span>Confianza {Number(h.confidence).toFixed(2)}</span>
                  ) : null}
                  {h.script ? <span>{h.script}</span> : null}
                </div>
                {h.source_ref || h.reason ? (
                  <div className="mt-1 break-all text-xs text-muted-foreground">
                    {[h.source_ref, h.reason].filter(Boolean).join(" · ")}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        ),
    },
  );

  return (
    <EntityTabs
      ariaLabel="Expediente de la persona"
      defaultValue={defaultTab}
      panels={panels}
    />
  );
}
