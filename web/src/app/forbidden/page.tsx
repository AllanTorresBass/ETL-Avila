import Link from "next/link";
import { signOut } from "@/app/sign-in/actions";

export default function ForbiddenPage() {
  return (
    <div className="rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
      <p className="text-lg font-medium text-foreground">Acceso restringido</p>
      <p className="mt-2 text-sm text-muted-foreground">
        Tu rol no incluye esta sección. Un super admin puede cambiarlo en Acceso.
      </p>
      <div className="mt-6 flex items-center justify-center gap-3">
        <Link
          href="/etl"
          className="btn-green-gradient inline-flex rounded-full px-5 py-2.5 text-xs font-medium text-white"
        >
          Volver al lector
        </Link>
        <form action={signOut}>
          <button
            type="submit"
            className="rounded-full border border-border px-5 py-2.5 text-xs font-medium text-brand"
          >
            Salir
          </button>
        </form>
      </div>
    </div>
  );
}
