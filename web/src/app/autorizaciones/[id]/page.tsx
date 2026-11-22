import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AuthorizationDetailView } from "@/components/authorization-detail";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { PageHeader } from "@/components/page-header";
import { can } from "@/lib/access";
import { requirePermission } from "@/lib/auth";
import { getAuthorizationDetail, getAuthorizationPageTitle } from "@/lib/authorization-data";
import { formatAuthHeading } from "@/lib/format";
import { firstParam } from "@/lib/list-params";

export const dynamic = "force-dynamic";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const NOTICES: Record<string, string> = {
  missing: "La autorización o la factura ya no existe, o la línea no tenía factura.",
  duplicate: "Esta línea es una copia; vincula la solicitud original.",
  account_mismatch: "La factura es de otra aseguradora. Elige una factura de la misma aseguradora.",
};

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const title = UUID.test(id) ? await getAuthorizationPageTitle(id) : null;
  return { title: title ? `${title} · Autorizaciones · Ávila GPS` : "Autorización · Ávila GPS" };
}

export default async function AutorizacionDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ aviso?: string }>;
}) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  const user = await requirePermission("read");
  const detail = await getAuthorizationDetail(id);
  if (!detail) notFound();

  const notice = NOTICES[firstParam((await searchParams).aviso)];
  const heading = formatAuthHeading({ aps_code: detail.line.aps_code, clave_rms: detail.line.clave_rms });
  const eyebrow = [detail.line.account_name, detail.line.contratante].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/autorizaciones", label: "Autorizaciones" },
          { label: heading },
        ]}
      />
      <PageHeader
        eyebrow={eyebrow || "Autorización"}
        title={heading}
        description="De qué libro viene, a quién cubre, qué factura la cobra y cada cambio que tuvo."
      />
      {notice ? (
        <p role="alert" className="rounded-2xl border border-warning/40 bg-warning-soft px-4 py-3 text-sm text-warning">
          {notice}
        </p>
      ) : null}
      <AuthorizationDetailView detail={detail} canReview={can(user.role, "review")} />
    </div>
  );
}
