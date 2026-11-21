import { API_UUID, notFound } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { getMedicoDetail } from "@/lib/medico-data";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;

  const { id } = await context.params;
  if (!API_UUID.test(id)) return notFound();
  const detail = await getMedicoDetail(id);
  if (!detail) return notFound();
  return Response.json(detail);
}
