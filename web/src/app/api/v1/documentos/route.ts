import { NextRequest, NextResponse } from "next/server";
import { LIST_PAGE_SIZE, requestedPage } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { DOCUMENT_TYPE_LABELS } from "@/lib/document-labels";
import { queryDocumentoList } from "@/lib/document-data";
import { normalizeQuery } from "@/lib/list-params";

export const dynamic = "force-dynamic";

const UPLOAD_STATUSES = ["pending", "uploaded", "failed", "skipped"] as const;

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const type = (sp.get("type") || "").trim();
  const uploadStatus = (sp.get("upload_status") || "").trim();
  const result = await queryDocumentoList({
    typeOk: type in DOCUMENT_TYPE_LABELS ? type : "",
    statusOk: (UPLOAD_STATUSES as readonly string[]).includes(uploadStatus) ? uploadStatus : "",
    account: (sp.get("account") || "").trim(),
    query: normalizeQuery(sp.get("q") || undefined),
    pageSize: LIST_PAGE_SIZE,
    requestedPage: requestedPage(sp.get("page")),
  });

  return NextResponse.json({
    accounts: result.accounts,
    types: result.types,
    statusCounts: result.statusCounts,
    total: result.total,
    page: result.page,
    pageSize: LIST_PAGE_SIZE,
    rows: result.docs,
  });
}
