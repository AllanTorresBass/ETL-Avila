import { NextRequest } from "next/server";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { parseRange } from "@/lib/dashboard-data";
import { getInformeData } from "@/lib/informe-data";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;
  const range = parseRange(request.nextUrl.searchParams.get("range") || undefined);
  return Response.json(await getInformeData(range));
}
