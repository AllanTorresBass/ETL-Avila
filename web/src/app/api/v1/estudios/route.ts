import { NextRequest, NextResponse } from "next/server";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { LIST_PAGE_SIZE } from "@/lib/api-http";
import { estudioListPage, isEstudioDetail, isEstudioFamily, queryEstudioList } from "@/lib/estudio-data";
import { normalizeQuery } from "@/lib/list-params";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const family = sp.get("familia") || "";
  const detail = sp.get("detalle") || "";
  const result = await queryEstudioList({
    query: normalizeQuery(sp.get("q") || undefined),
    family: isEstudioFamily(family) ? family : "",
    procedure: sp.get("procedimiento") || "",
    detail: isEstudioDetail(detail) ? detail : "",
    page: estudioListPage(sp.get("page")),
  });

  return NextResponse.json({
    total: result.total,
    page: result.page,
    pageSize: LIST_PAGE_SIZE,
    rows: result.rows,
  });
}
