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

export async function signIn(
  prev: { attempt: number } | null,
  formData: FormData,
): Promise<{ error: string; attempt: number }> {
  const email = String(formData.get("email") || "").trim().toLowerCase();
  const password = String(formData.get("password") || "");
  const next = safeNext(String(formData.get("next") || ""));
  const attempt = (prev?.attempt ?? 0) + 1;
  const failed = { error: "El correo o la contraseña no coinciden. Revísalos e intenta de nuevo.", attempt };

  await deleteExpiredSessions();
  const user = await findStaffByEmail(email);
  const valid = await verifyPassword(password, user?.password_hash || (await rejectHash()));
  if (!user || !user.active || !isAppRole(user.role) || !valid) return failed;

  await createSession(user.id);
  const destination = canAccessPath(user.role, next) ? next : "/etl";
  redirect(destination);
}

export async function signOut() {
  await destroySession();
  redirect("/sign-in");
}
