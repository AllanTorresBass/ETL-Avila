import Link from "next/link";

export default function ForbiddenPage() {
  return (
    <div className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
      <p className="text-lg font-medium text-[#0A2A6B]">Acceso restringido</p>
      <p className="mt-2 text-sm text-slate-500">
        Tu cuenta de Clerk no está en la lista de personal autorizado (CLERK_ALLOWED_EMAILS).
      </p>
      <Link
        href="/sign-in"
        className="btn-green-gradient mt-6 inline-flex rounded-full px-5 py-2.5 text-xs font-medium text-white"
      >
        Cambiar de cuenta
      </Link>
    </div>
  );
}
