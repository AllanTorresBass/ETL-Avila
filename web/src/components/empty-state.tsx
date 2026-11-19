export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}
