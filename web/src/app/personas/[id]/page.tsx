import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/breadcrumbs";
import { PersonaDossierTabs, PersonaSummary } from "@/components/persona-dossier";
import {
  getPersonaDetail,
  getPersonaPageTitle,
  resolvePersonaDefaultTab,
} from "@/lib/persona-data";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const title = await getPersonaPageTitle(id);
  if (!title) return { title: "Persona · Ávila GPS" };
  return { title: `${title} · Personas · Ávila GPS` };
}

export default async function PersonaDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ authPage?: string; tab?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const detail = await getPersonaDetail(id, sp.authPage);
  if (!detail) notFound();

  const defaultTab = resolvePersonaDefaultTab(sp.tab, detail);
  const crumbLabel =
    detail.person.full_name?.trim() || detail.person.identity_number || "Persona";

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { href: "/", label: "Inicio" },
          { href: "/personas", label: "Personas" },
          { label: crumbLabel },
        ]}
      />

      <PersonaSummary detail={detail} personId={id} />

      <Suspense
        fallback={
          <div className="h-64 animate-pulse rounded-3xl border border-border bg-muted/40" />
        }
      >
        <PersonaDossierTabs detail={detail} personId={id} defaultTab={defaultTab} />
      </Suspense>
    </div>
  );
}
