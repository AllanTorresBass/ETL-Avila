"use server";

import { redirect } from "next/navigation";
import { canAccessPath, isAppRole } from "@/lib/access";
import { hashPassword, verifyPassword } from "@/lib/password";
import { createSession, destroySession } from "@/lib/session";
import { deleteExpiredSessions, findStaffByEmail } from "@/lib/user-data";

function safeNext(value: string): string {
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/sign-in")) return "/etl";
  return value;
}

let dummyHash: string | null = null;

async function rejectHash(): Promise<string> {
  if (!dummyHash) dummyHash = await hashPassword("not-a-real-password");
  return dummyHash;
}

export async function signIn(formData: FormData) {
  const email = String(formData.get("email") || "").trim().toLowerCase();
  const password = String(formData.get("password") || "");
  const next = safeNext(String(formData.get("next") || ""));
  const failed = `/sign-in?error=1${next !== "/etl" ? `&next=${encodeURIComponent(next)}` : ""}`;

  await deleteExpiredSessions();
  const user = await findStaffByEmail(email);
  const valid = await verifyPassword(password, user?.password_hash || (await rejectHash()));
  if (!user || !user.active || !isAppRole(user.role) || !valid) redirect(failed);

  await createSession(user.id);
  const destination = canAccessPath(user.role, next) ? next : "/etl";
  redirect(destination);
}

export async function signOut() {
  await destroySession();
  redirect("/sign-in");
}
