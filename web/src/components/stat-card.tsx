import { Card, CardContent } from "@/components/ui/card";

export function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="rounded-3xl border-slate-100 bg-white shadow-sm">
      <CardContent className="p-6">
        <div className="text-2xl font-semibold tracking-tight text-[#0A2A6B] tabular-nums">
          {typeof value === "number" ? value.toLocaleString("es-VE") : value}
        </div>
        <div className="mt-2 text-xs font-medium uppercase tracking-wider text-slate-500">
          {label}
        </div>
      </CardContent>
    </Card>
  );
}
