export function SectionNav({
  items,
}: {
  items: { id: string; label: string; count: number }[];
}) {
  const visible = items.filter((i) => i.count > 0);
  if (visible.length < 2) return null;

  return (
    <nav
      aria-label="Secciones relacionadas"
      className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
    >
      {visible.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          className="shrink-0 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-brand hover:border-brand/40"
        >
          {item.label}{" "}
          <span className="tabular-nums text-muted-foreground">({item.count})</span>
        </a>
      ))}
    </nav>
  );
}
