import { NextRequest, NextResponse } from "next/server";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { getAuthorizationAnalytics, getAuthorizationKpis, queryAuthorizationList } from "@/lib/authorization-data";
import { authorizationListFilters, autorizacionFilterParams } from "@/lib/authorization-filters";
import { BI_RANGES, parseRange } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

/** `?vista=analisis&rango=12m` returns KPIs and the analysis; otherwise the filtered list. */
export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  if (sp.get("vista") === "analisis") {
    const range = sp.get("rango") ? parseRange(sp.get("rango") || undefined) : "todo";
    const months = BI_RANGES.find((r) => r.id === range)?.months ?? 0;
    const [kpis, analytics] = await Promise.all([getAuthorizationKpis(), getAuthorizationAnalytics(months)]);
    return NextResponse.json({ range, kpis, analytics });
  }

  const params = autorizacionFilterParams(Object.fromEntries(sp.entries()));
  const result = await queryAuthorizationList(
    authorizationListFilters(params, LIST_PAGE_SIZE, requestedPage(sp.get("page"))),
  );
  return NextResponse.json({
    total: result.total,
    page: result.page,
    pageSize: LIST_PAGE_SIZE,
    rows: result.rows,
  });
}
