import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/session";
import { signIn } from "./actions";

export const metadata: Metadata = {
  title: "Entrar · Ávila GPS",
};

export const dynamic = "force-dynamic";

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
    <div className="mx-auto flex min-h-[70vh] max-w-md items-center py-12">
      <section className="w-full rounded-3xl border border-border bg-card p-8 shadow-sm">
        <p className="text-xs font-medium tracking-wider text-info uppercase">Personal</p>
        <h1 className="mt-1 text-3xl font-medium tracking-tight">Entrar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          El super admin crea las demás cuentas y les asigna un rol.
        </p>
        <form action={signIn} className="mt-6 space-y-4">
          {next ? <input type="hidden" name="next" value={next} /> : null}
          <label className="block text-xs font-medium text-muted-foreground">
            Correo
            <input
              name="email"
              type="email"
              required
              autoComplete="username"
              className="mt-1 block w-full rounded-xl border border-border bg-card px-4 py-2.5 text-sm text-foreground"
            />
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Contraseña
            <input
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="mt-1 block w-full rounded-xl border border-border bg-card px-4 py-2.5 text-sm text-foreground"
            />
          </label>
          {sp.error ? (
            <p role="alert" className="text-sm text-danger">
              Correo o contraseña incorrectos.
            </p>
          ) : null}
          <button
            type="submit"
            className="btn-green-gradient w-full rounded-full px-5 py-2.5 text-sm font-medium text-white"
          >
            Entrar
          </button>
        </form>
      </section>
    </div>
  );
}
