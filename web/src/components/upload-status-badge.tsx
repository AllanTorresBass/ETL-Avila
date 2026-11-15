import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, { label: string; className: string }> = {
  uploaded: {
    label: "Subido",
    className: "bg-[#6CC24A]/15 text-[#0F7A33] hover:bg-[#6CC24A]/15",
  },
  failed: {
    label: "Fallido — reintentar carga",
    className: "bg-red-50 text-red-700 hover:bg-red-50",
  },
  pending: {
    label: "Pendiente",
    className: "bg-amber-50 text-amber-800 hover:bg-amber-50",
  },
};

export function UploadStatusBadge({ status }: { status: string | null | undefined }) {
  const key = (status || "pending").toLowerCase();
  const meta = LABELS[key] || {
    label: status || "Desconocido",
    className: "bg-slate-100 text-slate-600 hover:bg-slate-100",
  };
  return (
    <Badge className={`rounded-full ${meta.className}`}>{meta.label}</Badge>
  );
}
