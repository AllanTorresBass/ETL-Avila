import { NextRequest, NextResponse } from "next/server";
import { requestedPage } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { REVIEW_GROUPS } from "@/lib/review";
import { queryReviewQueue } from "@/lib/review-queue-data";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 20;
const STATUSES = new Set(["open", "accepted", "rejected"]);

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("review");
  if (isApiDenial(gate)) return gate;

  const sp = request.nextUrl.searchParams;
  const group = REVIEW_GROUPS.find((item) => item.id === (sp.get("tipo") || "").trim());
  const rawStatus = (sp.get("estado") || "").trim();
  const status = STATUSES.has(rawStatus) ? rawStatus : "open";
  const kinds = group ? group.kinds : REVIEW_GROUPS.flatMap((item) => item.kinds);
  const result = await queryReviewQueue({
    status,
    kinds,
    pageSize: PAGE_SIZE,
    requestedPage: requestedPage(sp.get("page")),
  });

  return NextResponse.json({
    status,
    tipo: group?.id ?? null,
    counts: result.counts,
    total: result.total,
    page: result.page,
    pageSize: PAGE_SIZE,
    rows: result.items,
  });
}
