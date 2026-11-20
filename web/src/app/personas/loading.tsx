export default function PersonasLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Cargando personas">
      <div className="space-y-2">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-muted" />
        <div className="h-4 w-80 max-w-full animate-pulse rounded-lg bg-muted" />
      </div>
      <div className="h-24 animate-pulse rounded-3xl border border-border bg-muted/50" />
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-16 animate-pulse rounded-2xl border border-border bg-muted/40"
            style={{ animationDelay: `${i * 40}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
