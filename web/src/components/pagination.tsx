import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

export const DEFAULT_PAGE_SIZE = 48;

export function parsePage(raw: string | undefined): number {
  const n = Number.parseInt(raw || "1", 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

/** Clamp a 1-based page into the valid range for the result set. */
export function clampPage(page: number, total: number, pageSize: number): number {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  return Math.min(Math.max(1, page), totalPages);
}

export function pageRange(page: number, pageSize: number, shown: number, total: number) {
  if (total <= 0 || shown <= 0) return { from: 0, to: 0, totalPages: 1 };
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, (page - 1) * pageSize + shown);
  return { from, to, totalPages };
}

/** Build a compact window of page numbers with ellipsis markers (-1). */
export function visiblePageNumbers(current: number, totalPages: number, sibling = 1): number[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages = new Set<number>();
  pages.add(1);
  pages.add(totalPages);
  for (let p = current - sibling; p <= current + sibling; p++) {
    if (p >= 1 && p <= totalPages) pages.add(p);
  }
  // Keep edges readable near the ends.
  if (current <= 3) {
    pages.add(2);
    pages.add(3);
    pages.add(4);
  }
  if (current >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
    pages.add(totalPages - 3);
  }

  const sorted = [...pages].sort((a, b) => a - b);
  const withGaps: number[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const n = sorted[i]!;
    if (i > 0 && n - sorted[i - 1]! > 1) withGaps.push(-1);
    withGaps.push(n);
  }
  return withGaps;
}

function buildHref(
  basePath: string,
  searchParams: Record<string, string | undefined>,
  pageParam: string,
  page: number,
  hash?: string,
) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(searchParams)) {
    if (v && k !== pageParam) params.set(k, v);
  }
  if (page > 1) params.set(pageParam, String(page));
  const qs = params.toString();
  const path = qs ? `${basePath}?${qs}` : basePath;
  return hash ? `${path}#${hash.replace(/^#/, "")}` : path;
}

/**
 * Numbered offset pagination with range summary.
 * Keeps filters in the URL; uses `pageParam` (default `page`) for the page key.
 */
export function Pagination({
  page,
  pageSize,
  total,
  basePath,
  searchParams,
  pageParam = "page",
  shown,
  hash,
}: {
  page: number;
  pageSize: number;
  total: number;
  basePath: string;
  searchParams: Record<string, string | undefined>;
  /** Query key for the page number (e.g. `authPage` on persona dossier). */
  pageParam?: string;
  /** Rows on the current page; defaults to a full page estimate. */
  shown?: number;
  /** Optional hash (e.g. `lista`) so paging keeps the viewport on the list. */
  hash?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  if (totalPages <= 1 || total <= 0) return null;

  const safePage = clampPage(page, total, pageSize);
  const estimatedShown = shown ?? Math.min(pageSize, total - (safePage - 1) * pageSize);
  const { from, to } = pageRange(safePage, pageSize, estimatedShown, total);
  const numbers = visiblePageNumbers(safePage, totalPages);
  const hrefFor = (p: number) => buildHref(basePath, searchParams, pageParam, p, hash);

  const pill =
    "inline-flex min-h-9 min-w-9 items-center justify-center rounded-full border border-border bg-card px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
  const pillActive = "bg-brand text-primary-foreground border-transparent hover:bg-brand";
  const pillMuted = `${pill} text-muted-foreground`;

  return (
    <nav
      aria-label="Paginación"
      className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
    >
      <p className="text-xs text-muted-foreground">
        Mostrando{" "}
        <span className="font-medium tabular-nums text-foreground">
          {from.toLocaleString("es-VE")}–{to.toLocaleString("es-VE")}
        </span>{" "}
        de <span className="font-medium tabular-nums text-foreground">{total.toLocaleString("es-VE")}</span>
        <span className="text-muted-foreground">
          {" "}
          · Página {safePage} de {totalPages}
        </span>
      </p>

      <div className="flex flex-wrap items-center gap-1.5">
        <Link
          href={hrefFor(Math.max(1, safePage - 1))}
          aria-label="Página anterior"
          aria-disabled={safePage <= 1 || undefined}
          tabIndex={safePage <= 1 ? -1 : undefined}
          className={safePage <= 1 ? `${pillMuted} pointer-events-none opacity-40` : pillMuted}
        >
          <ChevronLeft aria-hidden className="size-4" />
          <span className="sr-only sm:not-sr-only sm:ml-1">Anterior</span>
        </Link>

        {numbers.map((n, idx) =>
          n < 0 ? (
            <span
              key={`gap-${idx}`}
              aria-hidden
              className="inline-flex min-w-8 justify-center px-1 text-xs text-muted-foreground"
            >
              …
            </span>
          ) : (
            <Link
              key={n}
              href={hrefFor(n)}
              aria-label={`Página ${n}`}
              aria-current={n === safePage ? "page" : undefined}
              className={n === safePage ? `${pill} ${pillActive}` : pillMuted}
            >
              {n}
            </Link>
          ),
        )}

        <Link
          href={hrefFor(Math.min(totalPages, safePage + 1))}
          aria-label="Página siguiente"
          aria-disabled={safePage >= totalPages || undefined}
          tabIndex={safePage >= totalPages ? -1 : undefined}
          className={
            safePage >= totalPages ? `${pillMuted} pointer-events-none opacity-40` : pillMuted
          }
        >
          <span className="sr-only sm:not-sr-only sm:mr-1">Siguiente</span>
          <ChevronRight aria-hidden className="size-4" />
        </Link>
      </div>
    </nav>
  );
}
