import { NextResponse } from "next/server";
import { badRequest, isRecord, readJson, textField } from "@/lib/api-http";
import { isApiDenial, requireApiPermission } from "@/lib/auth";
import { createStaffAccount, listStaffUsers } from "@/lib/user-data";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireApiPermission("manage_users");
  if (isApiDenial(gate)) return gate;
  return NextResponse.json({ rows: await listStaffUsers() });
}

export async function POST(request: Request) {
  const gate = await requireApiPermission("manage_users");
  if (isApiDenial(gate)) return gate;

  const body = await readJson(request);
  if (!isRecord(body)) return badRequest("datos");
  const error = await createStaffAccount({
    email: textField(body.email),
    password: textField(body.password),
    role: textField(body.role),
    fullName: textField(body.full_name),
  });
  if (error) return badRequest(error);
  return NextResponse.json({ ok: true }, { status: 201 });
}
