import Link from "next/link";
import type { ReactNode } from "react";
import { CollapsibleSection } from "@/components/collapsible-section";
import { EmptyState } from "@/components/empty-state";

export function RelationSection({
  id,
  title,
  count,
  emptyTitle,
  emptyHint,
  moreHref,
  moreLabel = "Ver todos",
  footer,
  collapsible = false,
  children,
}: {
  id?: string;
  title: string;
  count: number;
  emptyTitle: string;
  emptyHint: string;
  moreHref?: string;
  moreLabel?: string;
  footer?: ReactNode;
  collapsible?: boolean;
  children?: ReactNode;
}) {
  const body = (
    <>
      {count === 0 ? <EmptyState title={emptyTitle} hint={emptyHint} /> : children}
      {footer}
    </>
  );

  if (collapsible) {
    return (
      <CollapsibleSection
        id={id}
        title={title}
        count={count}
        moreHref={moreHref}
        moreLabel={moreLabel}
      >
        {body}
      </CollapsibleSection>
    );
  }

  return (
    <section id={id} className="scroll-mt-24 space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-xl font-medium text-[#0A2A6B]">
          {title}{" "}
          <span className="tabular-nums text-slate-400">({count})</span>
        </h2>
        {moreHref ? (
          <Link href={moreHref} className="text-xs font-medium text-[#033CA0]">
            {moreLabel}
          </Link>
        ) : null}
      </div>
      {body}
    </section>
  );
}
