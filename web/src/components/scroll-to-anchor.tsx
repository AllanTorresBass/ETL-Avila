"use client";

import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/** After filter navigation, scroll the viewport to a named list anchor. */
export function ScrollToAnchor({ id }: { id: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.hash.replace(/^#/, "") !== id) return;

    const frame = window.requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [id, pathname, searchParams]);

  return null;
}
