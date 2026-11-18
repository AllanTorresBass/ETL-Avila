"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PreviewDialog, type PreviewItem } from "@/components/preview-dialog";
import { UploadStatusBadge } from "@/components/upload-status-badge";
import { DOCUMENT_TYPE_LABELS } from "@/lib/document-labels";

export type GalleryDoc = {
  id: string;
  documentType: string;
  pageIndex?: number | null;
  uploadStatus?: string | null;
  subtitle?: string;
};

export type GalleryBlock = {
  id: string;
  title?: string;
  meta?: string;
  href?: string;
  docs: GalleryDoc[];
};

function groupByType(docs: GalleryDoc[]) {
  const groups = new Map<string, GalleryDoc[]>();
  for (const doc of docs) {
    const key = doc.documentType || "otro_anexo";
    const list = groups.get(key) || [];
    list.push(doc);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

function PreviewTile({
  doc,
  onOpen,
}: {
  doc: GalleryDoc;
  onOpen: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const label = DOCUMENT_TYPE_LABELS[doc.documentType] || doc.documentType;
  const canPreview = doc.uploadStatus === "uploaded" && !failed;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="overflow-hidden rounded-2xl border border-slate-100 bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-[#5BB2F5]/40 hover:shadow-md"
    >
      <div className="h-40 bg-slate-100">
        {canPreview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/blob/${doc.id}`}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover object-top"
            onError={() => setFailed(true)}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-3 text-center text-xs text-slate-500">
            Vista no disponible
          </div>
        )}
      </div>
      <div className="space-y-1 p-3">
        <div className="text-sm font-medium text-[#033CA0]">{label}</div>
        {doc.subtitle ? <div className="text-xs text-slate-500">{doc.subtitle}</div> : null}
        {doc.pageIndex != null ? (
          <div className="text-xs text-slate-500">Página {doc.pageIndex}</div>
        ) : null}
        {doc.uploadStatus && doc.uploadStatus !== "uploaded" ? (
          <UploadStatusBadge status={doc.uploadStatus} />
        ) : null}
      </div>
    </button>
  );
}

export function DocumentGallery({ blocks }: { blocks: GalleryBlock[] }) {
  const [index, setIndex] = useState<number | null>(null);

  const items = useMemo(() => {
    const flat = blocks.flatMap((block) => groupByType(block.docs).flatMap(([, docs]) => docs));
    return flat.map((doc): PreviewItem => {
      const label = DOCUMENT_TYPE_LABELS[doc.documentType] || doc.documentType;
      const page = doc.pageIndex != null ? `Página ${doc.pageIndex}` : null;
      return {
        id: doc.id,
        title: label,
        meta: [doc.subtitle, page].filter(Boolean).join(" · ") || undefined,
        canPreview: doc.uploadStatus === "uploaded",
      };
    });
  }, [blocks]);

  const indexById = useMemo(() => {
    const map = new Map<string, number>();
    items.forEach((item, itemIndex) => map.set(item.id, itemIndex));
    return map;
  }, [items]);

  return (
    <>
      <div className="space-y-6">
        {blocks.map((block) => (
          <div key={block.id} className="space-y-3">
            {block.title || block.meta ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  {block.title ? (
                    <h3 className="text-sm font-medium">
                      {block.href ? (
                        <Link
                          href={block.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#033CA0] hover:underline"
                        >
                          {block.title}
                        </Link>
                      ) : (
                        <span className="text-[#0A2A6B]">{block.title}</span>
                      )}
                    </h3>
                  ) : null}
                  {block.meta ? <p className="text-xs text-slate-500">{block.meta}</p> : null}
                </div>
              </div>
            ) : null}
            {block.docs.length === 0 ? (
              <p className="text-sm text-slate-500">Sin páginas cargadas para esta factura.</p>
            ) : null}
            <div className="space-y-5">
              {groupByType(block.docs).map(([type, docs]) => (
                <div key={`${block.id}-${type}`} className="space-y-2">
                  <h3 className="text-xs font-medium tracking-wider text-slate-500 uppercase">
                    {DOCUMENT_TYPE_LABELS[type] || type}{" "}
                    <span className="tabular-nums text-slate-400">({docs.length})</span>
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {docs.map((doc) => (
                      <PreviewTile
                        key={doc.id}
                        doc={doc}
                        onOpen={() => setIndex(indexById.get(doc.id) ?? 0)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <PreviewDialog
        items={items}
        index={index}
        onIndex={setIndex}
        onClose={() => setIndex(null)}
      />
    </>
  );
}
