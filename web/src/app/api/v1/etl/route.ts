import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { getEtlData } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;
  return Response.json(await getEtlData());
}
