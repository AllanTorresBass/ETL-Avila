"use server";

import { redirect } from "next/navigation";
import { requirePermission } from "@/lib/auth";
import { createSession } from "@/lib/session";
import { createStaffAccount, updateStaffAccount, type StaffAccountError } from "@/lib/user-data";

function fail(code: StaffAccountError): never {
  redirect(`/usuarios?error=${code}`);
}

export async function createUser(formData: FormData) {
  await requirePermission("manage_users");
  const error = await createStaffAccount({
    email: String(formData.get("email") || ""),
    password: String(formData.get("password") || ""),
    role: String(formData.get("role") || ""),
    fullName: String(formData.get("full_name") || ""),
  });
  if (error) fail(error);
  redirect("/usuarios?ok=creada");
}

export async function updateUser(formData: FormData) {
  const actor = await requirePermission("manage_users");
  const id = String(formData.get("id") || "");
  const result = await updateStaffAccount(actor.id, {
    id,
    role: String(formData.get("role") || ""),
    active: formData.get("active") === "1",
    password: String(formData.get("password") || ""),
    fullName: String(formData.get("full_name") || ""),
  });
  if (result.error) fail(result.error);
  if (result.rotateSession) await createSession(id);
  redirect("/usuarios?ok=actualizada");
}
