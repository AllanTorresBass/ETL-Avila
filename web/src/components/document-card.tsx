import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { DOCUMENT_TYPE_LABELS } from "@/lib/db";
import { UploadStatusBadge } from "@/components/upload-status-badge";

export function DocumentCard({
  id,
  documentType,
  pageIndex,
  uploadStatus,
  subtitle,
}: {
  id: string;
  documentType: string;
  pageIndex?: number | null;
  uploadStatus?: string | null;
  subtitle?: string;
}) {
  const typeLabel = DOCUMENT_TYPE_LABELS[documentType] || documentType;
  const ilegible = documentType === "ilegible";

  return (
    <Link href={`/documentos/${id}`}>
      <Card className="rounded-3xl border-border shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
        <CardContent className="space-y-2 p-5">
          <div className="flex flex-wrap gap-2">
            <Badge
              className={`rounded-full ${
                ilegible
                  ? "bg-warning-soft text-warning hover:bg-warning-soft"
                  : "bg-brand/10 text-brand hover:bg-brand/10"
              }`}
            >
              {typeLabel}
            </Badge>
            {uploadStatus ? <UploadStatusBadge status={uploadStatus} /> : null}
          </div>
          {subtitle ? <div className="text-sm font-medium">{subtitle}</div> : null}
          {pageIndex != null ? (
            <div className="text-xs text-muted-foreground">Página {pageIndex}</div>
          ) : null}
        </CardContent>
      </Card>
    </Link>
  );
}
