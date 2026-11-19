import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, { label: string; className: string }> = {
  uploaded: {
    label: "Subido",
    className: "bg-success/15 text-success hover:bg-success/15",
  },
  failed: {
    label: "Fallido — reintentar carga",
    className: "bg-danger-soft text-danger hover:bg-danger-soft",
  },
  pending: {
    label: "Pendiente",
    className: "bg-warning-soft text-warning hover:bg-warning-soft",
  },
};

export function UploadStatusBadge({ status }: { status: string | null | undefined }) {
  const key = (status || "pending").toLowerCase();
  const meta = LABELS[key] || {
    label: status || "Desconocido",
    className: "bg-muted text-muted-foreground hover:bg-muted",
  };
  return (
    <Badge className={`rounded-full ${meta.className}`}>{meta.label}</Badge>
  );
}
