import { NextRequest, NextResponse } from "next/server";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { normalizeQuery, triState } from "@/lib/list-params";
import { queryPersonaList } from "@/lib/persona-list-data";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const query = normalizeQuery(sp.get("q") || undefined);
  const role = sp.get("role") || "";
  const roleFilter = role === "titular" || role === "beneficiario" || role === "unknown" ? role : "";
  const result = await queryPersonaList({
    query,
    like: `%${query}%`,
    hasCi: triState(sp.get("has_ci") || undefined),
    hasPhone: triState(sp.get("has_phone") || undefined),
    hasAuthorization: triState(sp.get("has_authorization") || undefined),
    hasInvoice: triState(sp.get("has_invoice") || undefined),
    hasContactGap: triState(sp.get("has_contact_gap") || undefined),
    incompleteName: triState(sp.get("incomplete_name") || undefined),
    roleFilter,
    account: (sp.get("account") || "").trim(),
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
