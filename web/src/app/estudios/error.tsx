"use client";

export default function EstudiosError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
      <p className="text-lg font-medium text-foreground">No se pudo cargar los estudios</p>
      <p className="mt-2 text-sm text-muted-foreground">
        Revisa la conexión a Neon o vuelve a intentar. No se registran cédulas ni nombres en logs.
      </p>
      <button
        type="button"
        onClick={reset}
        className="btn-green-gradient mt-6 rounded-full px-5 py-2.5 text-xs font-medium text-white"
      >
        Reintentar
      </button>
    </div>
  );
}
