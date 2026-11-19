"use client";

import { Dialog } from "radix-ui";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { DocumentPreview } from "@/components/document-preview";

export type PreviewItem = {
  id: string;
  title: string;
  meta?: string;
  canPreview: boolean;
};

export function PreviewDialog({
  items,
  index,
  onIndex,
  onClose,
}: {
  items: PreviewItem[];
  index: number | null;
  onIndex: (index: number) => void;
  onClose: () => void;
}) {
  const item = index != null ? items[index] : undefined;
  const open = item != null;

  useEffect(() => {
    if (!open || index == null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight" && index < items.length - 1) {
        event.preventDefault();
        onIndex(index + 1);
      } else if (event.key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        onIndex(index - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, index, items.length, onIndex]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-hero" />
        <Dialog.Content className="fixed inset-0 z-50 flex h-dvh w-screen max-w-none flex-col bg-hero outline-none">
          {item ? (
            <>
              <div className="flex items-center gap-3 px-4 py-3 text-white sm:px-6">
                <div className="min-w-0 flex-1">
                  <Dialog.Title className="truncate text-base font-medium">
                    {item.title}
                  </Dialog.Title>
                  <Dialog.Description className="truncate text-xs text-white/70">
                    {[item.meta, `${(index ?? 0) + 1} de ${items.length}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </Dialog.Description>
                </div>
                <Link
                  href={`/documentos/${item.id}`}
                  className="shrink-0 rounded-full border border-white/30 px-4 py-2 text-xs font-medium text-white"
                >
                  Abrir ficha
                </Link>
                <Dialog.Close className="rounded-full bg-card px-4 py-2 text-xs font-medium text-foreground">
                  <span className="inline-flex items-center gap-1">
                    <X className="size-3.5" aria-hidden />
                    Cerrar
                  </span>
                </Dialog.Close>
              </div>
              <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden px-14">
                {item.canPreview ? (
                  <DocumentPreview src={`/api/blob/${item.id}`} alt={item.title} fill />
                ) : (
                  <div className="flex h-full items-center justify-center px-6 text-center text-sm text-white/80">
                    Vista no disponible
                  </div>
                )}
                {index != null && index > 0 ? (
                  <button
                    type="button"
                    aria-label="Anterior"
                    onClick={() => onIndex(index - 1)}
                    className="absolute top-1/2 left-3 -translate-y-1/2 rounded-full bg-card p-3 text-foreground shadow-sm"
                  >
                    <ChevronLeft className="size-5" aria-hidden />
                  </button>
                ) : null}
                {index != null && index < items.length - 1 ? (
                  <button
                    type="button"
                    aria-label="Siguiente"
                    onClick={() => onIndex(index + 1)}
                    className="absolute top-1/2 right-3 -translate-y-1/2 rounded-full bg-card p-3 text-foreground shadow-sm"
                  >
                    <ChevronRight className="size-5" aria-hidden />
                  </button>
                ) : null}
              </div>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
