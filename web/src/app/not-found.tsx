import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-3xl border border-slate-100 bg-white p-8 text-center shadow-sm">
      <p className="text-lg font-medium text-[#0A2A6B]">No encontrado</p>
      <p className="mt-2 text-sm text-slate-500">La persona, factura o documento no existe en el inventario.</p>
      <Link
        href="/"
        className="btn-green-gradient mt-6 inline-flex rounded-full px-5 py-2.5 text-xs font-medium text-white"
      >
        Volver al inicio
      </Link>
    </div>
  );
}
