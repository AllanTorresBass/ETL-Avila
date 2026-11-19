import Link from "next/link";

export type Crumb = { href?: string; label: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Migas de pan" className="mb-3 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="flex items-center gap-1">
          {i > 0 ? <span aria-hidden>/</span> : null}
          {item.href ? (
            <Link href={item.href} className="text-brand hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-foreground/80" aria-current="page">
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
