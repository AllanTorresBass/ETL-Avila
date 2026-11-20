import { NextRequest, NextResponse } from "next/server";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { queryFacturaList } from "@/lib/factura-list-data";
import { normalizeQuery, triState } from "@/lib/list-params";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const query = normalizeQuery(sp.get("q") || undefined);
  const result = await queryFacturaList({
    query,
    like: `%${query}%`,
    account: (sp.get("account") || "").trim(),
    year: (sp.get("year") || "").trim(),
    month: (sp.get("month") || "").trim(),
    hasPerson: triState(sp.get("has_person") || undefined),
    hasTitular: triState(sp.get("has_titular") || undefined),
    hasDocs: triState(sp.get("has_docs") || undefined),
    pageSize: LIST_PAGE_SIZE,
    requestedPage: requestedPage(sp.get("page")),
    exportLimit: 0,
  });

  return NextResponse.json({
    total: result.total,
    page: result.page,
    pageSize: LIST_PAGE_SIZE,
    rows: result.pageRows,
  });
}
