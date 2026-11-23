import { authStatusLabel } from "@/lib/authorization-labels";

function tone(status: string | null, invoiceId: string | null): string {
  if (invoiceId) return "bg-success-soft text-success";
  if (status === "review" || status === "low_score") return "bg-warning-soft text-warning";
  if (status === "no_person") return "bg-danger-soft text-danger";
  return "bg-muted text-muted-foreground";
}

export function AuthorizationStatusPill({ status, invoiceId }: { status: string | null; invoiceId: string | null }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${tone(status, invoiceId)}`}>
      {authStatusLabel(status, invoiceId)}
    </span>
  );
}
