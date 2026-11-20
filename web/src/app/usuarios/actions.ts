"use server";

import { redirect } from "next/navigation";
import { isAppRole } from "@/lib/access";
import { requirePermission } from "@/lib/auth";
import { sql } from "@/lib/db";
import { hashPassword } from "@/lib/password";
import { createSession } from "@/lib/session";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const UUID = /^[0-9a-f-]{36}$/i;

function fail(code: string): never {
  redirect(`/usuarios?error=${code}`);
}

export async function createUser(formData: FormData) {
  await requirePermission("manage_users");
  const email = String(formData.get("email") || "").trim().toLowerCase();
  const password = String(formData.get("password") || "");
  const role = String(formData.get("role") || "");
  const fullName = String(formData.get("full_name") || "").trim().slice(0, 120);

  if (!EMAIL.test(email) || !isAppRole(role)) fail("datos");
  if (password.length < 8 || password.length > 200) fail("password");

  const db = sql();
  const [existing] = await db`SELECT id FROM avila.app_user WHERE email = ${email} LIMIT 1`;
  if (existing) fail("duplicate");

  await db`
    INSERT INTO avila.app_user (email, password_hash, full_name, role)
    VALUES (${email}, ${await hashPassword(password)}, ${fullName || null}, ${role})
  `;
  redirect("/usuarios?ok=creada");
}

export async function updateUser(formData: FormData) {
  const actor = await requirePermission("manage_users");
  const id = String(formData.get("id") || "");
  const role = String(formData.get("role") || "");
  const active = formData.get("active") === "1";
  const password = String(formData.get("password") || "");
  const fullName = String(formData.get("full_name") || "").trim().slice(0, 120);

  if (!UUID.test(id) || !isAppRole(role)) fail("datos");
  if (password && (password.length < 8 || password.length > 200)) fail("password");
  if (actor.id === id && !active) fail("self");

  const db = sql();
  const [target] = await db`
    SELECT id::text AS id, role FROM avila.app_user WHERE id = ${id}::uuid LIMIT 1
  `;
  if (!target) fail("datos");

  const removesSuperAdmin = target.role === "super_admin" && (role !== "super_admin" || !active);
  if (removesSuperAdmin) {
    const [count] = await db`
      SELECT count(*)::int AS n
      FROM avila.app_user
      WHERE role = 'super_admin' AND active = true AND id <> ${id}::uuid
    `;
    if ((count?.n ?? 0) < 1) fail("last");
  }

  if (password) {
    await db`
      UPDATE avila.app_user
      SET role = ${role},
          active = ${active},
          full_name = ${fullName || null},
          password_hash = ${await hashPassword(password)},
          updated_at = now()
      WHERE id = ${id}::uuid
    `;
    await db`DELETE FROM avila.app_session WHERE user_id = ${id}::uuid`;
    if (actor.id === id) await createSession(id);
  } else {
    await db`
      UPDATE avila.app_user
      SET role = ${role},
          active = ${active},
          full_name = ${fullName || null},
          updated_at = now()
      WHERE id = ${id}::uuid
    `;
    if (!active) await db`DELETE FROM avila.app_session WHERE user_id = ${id}::uuid`;
  }

  redirect("/usuarios?ok=actualizada");
}
