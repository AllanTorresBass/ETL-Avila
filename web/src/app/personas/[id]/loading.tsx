export default function PersonaDetailLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando persona">
      <div className="h-4 w-56 animate-pulse rounded bg-muted" />
      <div className="h-56 animate-pulse rounded-3xl border border-border bg-muted/50" />
      <div className="h-12 animate-pulse rounded-full bg-muted/60" />
      <div className="h-72 animate-pulse rounded-3xl border border-border bg-muted/40" />
    </div>
  );
}
