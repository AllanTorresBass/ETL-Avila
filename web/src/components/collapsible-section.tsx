"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function CollapsibleSection({
  id,
  title,
  count,
  moreHref,
  moreLabel = "Ver todos",
  children,
}: {
  id?: string;
  title: string;
  count: number;
  moreHref?: string;
  moreLabel?: string;
  children: ReactNode;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!id) return;

    const matches = (hash: string) => hash === `#${id}`;
    if (matches(window.location.hash)) setOpen(true);

    const onHash = () => {
      if (matches(window.location.hash)) setOpen(true);
    };
    const onClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (matches(anchor.hash)) setOpen(true);
    };

    window.addEventListener("hashchange", onHash);
    document.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("hashchange", onHash);
      document.removeEventListener("click", onClick);
    };
  }, [id]);

  return (
    <section id={id} className="scroll-mt-24">
      <div className="flex items-stretch rounded-3xl border border-slate-100 bg-white shadow-sm">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-3xl px-5 py-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5BB2F5]"
        >
          <h2 className="text-xl font-medium text-[#0A2A6B]">
            {title}{" "}
            <span className="tabular-nums text-slate-400">({count})</span>
          </h2>
          <ChevronDown
            aria-hidden
            className={cn(
              "size-5 shrink-0 text-[#0A2A6B] transition-transform",
              open && "rotate-180",
            )}
          />
        </button>
        {moreHref ? (
          <Link
            href={moreHref}
            className="self-center pr-5 text-xs font-medium text-[#033CA0]"
          >
            {moreLabel}
          </Link>
        ) : null}
      </div>
      <div id={panelId} hidden={!open} className="mt-3 space-y-3">
        {children}
      </div>
    </section>
  );
}
