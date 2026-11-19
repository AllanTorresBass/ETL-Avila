import { DocumentCard } from "@/components/document-card";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";

export type DocGroupItem = {
  id: string;
  document_type: string;
  page_index?: number | null;
  upload_status?: string | null;
  subtitle?: string;
};

export function DocumentTypeGroup({
  docs,
  groupBy = "type",
}: {
  docs: DocGroupItem[];
  groupBy?: "type" | "flat";
}) {
  if (groupBy === "flat") {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {docs.map((doc) => (
          <DocumentCard
            key={doc.id}
            id={doc.id}
            documentType={doc.document_type}
            pageIndex={doc.page_index}
            uploadStatus={doc.upload_status}
            subtitle={doc.subtitle}
          />
        ))}
      </div>
    );
  }

  const groups = new Map<string, DocGroupItem[]>();
  for (const doc of docs) {
    const key = doc.document_type || "otro_anexo";
    const list = groups.get(key) || [];
    list.push(doc);
    groups.set(key, list);
  }

  return (
    <div className="space-y-5">
      {[...groups.entries()].map(([type, items]) => (
        <div key={type} className="space-y-2">
          <h3 className="sticky top-16 z-10 -mx-1 bg-background/90 px-1 py-1 text-xs font-medium tracking-wider text-muted-foreground uppercase backdrop-blur">
            {DOCUMENT_TYPE_LABELS[type] || type}{" "}
            <span className="tabular-nums text-muted-foreground">({items.length})</span>
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((doc) => (
              <DocumentCard
                key={doc.id}
                id={doc.id}
                documentType={doc.document_type}
                pageIndex={doc.page_index}
                uploadStatus={doc.upload_status}
                subtitle={doc.subtitle}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
