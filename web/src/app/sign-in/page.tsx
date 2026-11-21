import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { FileText, ReceiptText, ShieldCheck, Users } from "lucide-react";
import { getCurrentUser } from "@/lib/session";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = {
  title: "Entrar · Ávila GPS",
};

export const dynamic = "force-dynamic";

const points = [
  { icon: Users, title: "Personas", text: "Cada titular con su grupo familiar, en un solo expediente." },
  { icon: ReceiptText, title: "Facturas", text: "Los servicios de cada paciente, ligados a quien los recibió." },
  { icon: FileText, title: "Documentos", text: "Cédulas, carnets y soportes listos para revisar según tu rol." },
];

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const user = await getCurrentUser();
  if (user) redirect("/etl");
  const sp = await searchParams;
  const next = sp.next && sp.next.startsWith("/") && !sp.next.startsWith("//") ? sp.next : "";

  return (
    <div data-screen="sign-in" className="flex w-full flex-1">
      <section className="grid w-full overflow-hidden rounded-3xl border border-border bg-card shadow-sm lg:min-h-[36rem] lg:grid-cols-[1.05fr_0.95fr]">
        <aside className="relative hidden overflow-hidden bg-hero px-10 py-12 text-hero-foreground lg:flex lg:flex-col lg:justify-between">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-20 -right-16 size-72 rounded-full bg-[#5BB2F5]/25 blur-3xl"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-16 -left-10 size-56 rounded-full bg-[#6CC24A]/20 blur-3xl"
          />
          <div className="relative rise-in" style={{ "--i": 0 } as CSSProperties}>
            <p className="inline-flex items-center gap-2 text-xs font-medium tracking-wider text-[#9ed4ff] uppercase">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Equipo Ávila GPS
            </p>
            <p className="mt-4 max-w-sm text-3xl font-medium tracking-tight">
              La atención integral empieza con <span className="text-[#5BB2F5]">información en orden</span>.
            </p>
            <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/75">
              Personas, facturas y documentos de cada paciente en un solo lugar, para atender con un enfoque humano,
              digno y cercano.
            </p>
          </div>
          <ul className="relative mt-10 space-y-4">
            {points.map((point, index) => (
              <li
                key={point.title}
                className="flex items-start gap-3 rise-in"
                style={{ "--i": index + 1 } as CSSProperties}
              >
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-2xl bg-white/10">
                  <point.icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span>
                  <span className="block text-sm font-medium">{point.title}</span>
                  <span className="mt-0.5 block text-sm text-white/70">{point.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </aside>
        <div className="flex flex-col justify-center px-6 py-10 sm:px-10">
          <div className="mb-8 rounded-2xl border border-border bg-muted/50 px-4 py-3 lg:hidden">
            <p className="text-xs font-medium tracking-wider text-info uppercase">Equipo Ávila GPS</p>
            <p className="mt-1 text-sm text-muted-foreground">
              La información de cada paciente, en orden y en un solo lugar.
            </p>
          </div>
          <SignInForm nextPath={next} initialError={sp.error === "1"} />
        </div>
      </section>
    </div>
  );
}
