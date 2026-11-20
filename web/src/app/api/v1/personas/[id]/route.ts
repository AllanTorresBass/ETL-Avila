import { NextRequest } from "next/server";
import { API_UUID, notFound } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { getPersonaDetail } from "@/lib/persona-data";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const { id } = await context.params;
  if (!API_UUID.test(id)) return notFound();
  const detail = await getPersonaDetail(id, request.nextUrl.searchParams.get("authPage") || undefined);
  if (!detail) return notFound();
  return Response.json(detail);
}
