import { NextRequest, NextResponse } from "next/server";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { normalizeQuery, triState } from "@/lib/list-params";
import { queryMedicoList } from "@/lib/medico-data";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const query = normalizeQuery(sp.get("q") || undefined);
  const result = await queryMedicoList({
    query,
    like: `%${query}%`,
    area: (sp.get("area") || "").trim(),
    especialidad: (sp.get("especialidad") || "").trim(),
    hasMpps: triState(sp.get("has_mpps") || undefined),
    pageSize: LIST_PAGE_SIZE,
    requestedPage: requestedPage(sp.get("page")),
  });

  return NextResponse.json({
    total: result.total,
    page: result.page,
    pageSize: LIST_PAGE_SIZE,
    rows: result.rows,
  });
}
