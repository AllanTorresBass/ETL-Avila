import { NextResponse } from "next/server";
import { badRequest, isRecord, readJson, textField } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { createSession } from "@/lib/session";
import { updateStaffAccount } from "@/lib/user-data";

export const dynamic = "force-dynamic";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const gate = await requireApiPermission("manage_users");
  if (isApiDenial(gate)) return gate;

  const { id } = await context.params;
  const body = await readJson(request);
  if (!isRecord(body)) return badRequest("datos");
  const result = await updateStaffAccount(gate.id, {
    id,
    role: textField(body.role),
    active: body.active === true || body.active === "1",
    password: textField(body.password),
    fullName: textField(body.full_name),
  });
  if (result.error) return badRequest(result.error);
  if (result.rotateSession) await createSession(id);
  return NextResponse.json({ ok: true });
}
