import { redirect } from "next/navigation";
import { NextResponse } from "next/server";
import { can, type Permission } from "@/lib/access";
import { getCurrentUser } from "@/lib/session";
import type { SessionUser } from "@/lib/session-db";

export async function requirePermission(permission: Permission): Promise<SessionUser> {
  const user = await getCurrentUser();
  if (!user) redirect("/sign-in");
  if (!can(user.role, permission)) redirect("/forbidden");
  return user;
}

/** JSON routes. Returns the staff user, or a 401/403 response. */
export async function requireApiPermission(
  permission: Permission,
): Promise<SessionUser | NextResponse> {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!can(user.role, permission)) return NextResponse.json({ error: "forbidden" }, { status: 403 });
  return user;
}

export function isApiDenial(result: SessionUser | NextResponse): result is NextResponse {
  return result instanceof NextResponse;
}

/** Document bytes: any active signed-in role. */
export async function requireReaderApi(): Promise<NextResponse | null> {
  const result = await requireApiPermission("read");
  return isApiDenial(result) ? result : null;
}
