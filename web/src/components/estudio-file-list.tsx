"use client";

import Link from "next/link";
import { useState } from "react";
import { PreviewDialog, type PreviewItem } from "@/components/preview-dialog";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface EstudioFileItem {
  id: string;
  title: string;
  meta: string;
  badges: string[];
  invoiceHref?: string;
  documentId: string;
  pageLabel: string | null;
  canPreview: boolean;
}

export interface EstudioFileListProps {
  items: EstudioFileItem[];
  className?: string;
}

function ExamThumb({
  item,
  onOpen,
}: {
  item: EstudioFileItem;
  onOpen: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const visible = item.canPreview && !failed;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Ver examen: ${item.title}`}
      className="relative h-28 w-24 shrink-0 overflow-hidden rounded-xl border border-border bg-muted"
    >
      {visible ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/blob/${item.documentId}`}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover object-top"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="flex h-full items-center justify-center px-2 text-center text-[11px] text-muted-foreground">
          Vista no disponible
        </span>
      )}
      {item.pageLabel ? (
        <span className="absolute inset-x-0 bottom-0 bg-hero/80 px-1 py-0.5 text-center text-[10px] font-medium text-white">
          {item.pageLabel}
        </span>
      ) : null}
    </button>
  );
}

export function EstudioFileList({ items, className }: EstudioFileListProps) {
  const [index, setIndex] = useState<number | null>(null);
  const previews: PreviewItem[] = items.map((item) => ({
    id: item.documentId,
    title: item.title,
    meta: [item.meta, item.pageLabel].filter(Boolean).join(" · ") || undefined,
    canPreview: item.canPreview,
  }));

  return (
    <>
      <div className={cn("space-y-2", className)}>
        {items.map((item, itemIndex) => (
          <article
            key={item.id}
            className="flex items-start gap-3 rounded-2xl border border-border bg-card p-3 text-sm shadow-sm"
          >
            <ExamThumb item={item} onOpen={() => setIndex(itemIndex)} />
            <div className="min-w-0 flex-1 space-y-1 py-0.5">
              <div className="flex flex-wrap items-center gap-2">
                {item.invoiceHref ? (
                  <Link href={item.invoiceHref} className="font-medium text-brand">
                    {item.title}
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => setIndex(itemIndex)}
                    className="text-left font-medium text-brand"
                  >
                    {item.title}
                  </button>
                )}
                {item.badges.map((badge) => (
                  <Badge key={badge} variant="secondary" className="rounded-full bg-brand/10 text-brand">
                    {badge}
                  </Badge>
                ))}
              </div>
              {item.meta ? <p className="text-xs text-muted-foreground">{item.meta}</p> : null}
              <button
                type="button"
                onClick={() => setIndex(itemIndex)}
                className="text-xs font-medium text-brand"
              >
                Ver examen
              </button>
            </div>
          </article>
        ))}
      </div>
      <PreviewDialog items={previews} index={index} onIndex={setIndex} onClose={() => setIndex(null)} />
    </>
  );
}
