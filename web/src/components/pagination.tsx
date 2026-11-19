import Link from "next/link";

export function Pagination({
  page,
  pageSize,
  total,
  basePath,
  searchParams,
}: {
  page: number;
  pageSize: number;
  total: number;
  basePath: string;
  searchParams: Record<string, string | undefined>;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  function hrefFor(p: number) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(searchParams)) {
      if (v) params.set(k, v);
    }
    if (p > 1) params.set("page", String(p));
    else params.delete("page");
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
      <p className="text-xs text-muted-foreground">
        Página {page} de {totalPages}
      </p>
      <div className="flex gap-2">
        {page > 1 ? (
          <Link
            href={hrefFor(page - 1)}
            className="rounded-full border border-border bg-card px-4 py-2 text-xs font-medium text-brand"
          >
            Anterior
          </Link>
        ) : null}
        {page < totalPages ? (
          <Link
            href={hrefFor(page + 1)}
            className="btn-green-gradient rounded-full px-4 py-2 text-xs font-medium text-white"
          >
            Siguiente
          </Link>
        ) : null}
      </div>
    </div>
  );
}

export function parsePage(raw: string | undefined): number {
  const n = Number.parseInt(raw || "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

export const DEFAULT_PAGE_SIZE = 48;
