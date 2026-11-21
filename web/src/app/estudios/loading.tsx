export default function EstudiosLoading() {
  return (
    <div className="space-y-6">
      <div className="h-16 animate-pulse rounded-3xl bg-muted" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-3xl bg-muted" />
        ))}
      </div>
      <div className="h-24 animate-pulse rounded-3xl bg-muted" />
      <div className="space-y-2">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-2xl bg-muted" />
        ))}
      </div>
    </div>
  );
}
