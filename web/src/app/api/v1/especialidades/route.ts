import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { getEspecialidadTree, listEspecialidadSpecialists } from "@/lib/medico-data";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireApiPermission("read");
  if (isApiDenial(gate)) return gate;
  const [rows, specialists] = await Promise.all([getEspecialidadTree(), listEspecialidadSpecialists()]);
  return Response.json({ rows, specialists });
}
