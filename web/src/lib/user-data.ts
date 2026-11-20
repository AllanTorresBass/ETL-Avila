import { isAppRole, type AppRole } from "@/lib/access";
import { sql } from "@/lib/db";
import { hashPassword } from "@/lib/password";

export type StaffUserRow = {
  id: string;
  email: string;
  full_name: string | null;
  role: AppRole;
  active: boolean;
};

export async function listStaffUsers(): Promise<StaffUserRow[]> {
  const db = sql();
  const rows = await db`
    SELECT id::text AS id, email, full_name, role, active
    FROM avila.app_user
    ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'revisor' THEN 1 ELSE 2 END, email
  `;
  return rows as StaffUserRow[];
}

export async function deleteExpiredSessions(): Promise<void> {
  const db = sql();
  await db`DELETE FROM avila.app_session WHERE expires_at < now()`;
}

export async function findStaffByEmail(email: string): Promise<{
  id: string;
  password_hash: string;
  role: string;
  active: boolean;
} | null> {
  const db = sql();
  const [user] = await db`
    SELECT id::text AS id, password_hash, role, active
    FROM avila.app_user
    WHERE email = ${email}
    LIMIT 1
  `;
  return (user as { id: string; password_hash: string; role: string; active: boolean } | undefined) ?? null;
}

export async function staffEmailTaken(email: string): Promise<boolean> {
  const db = sql();
  const [existing] = await db`SELECT id FROM avila.app_user WHERE email = ${email} LIMIT 1`;
  return Boolean(existing);
}

export async function insertStaffUser(input: {
  email: string;
  passwordHash: string;
  fullName: string | null;
  role: AppRole;
}): Promise<void> {
  const db = sql();
  await db`
    INSERT INTO avila.app_user (email, password_hash, full_name, role)
    VALUES (${input.email}, ${input.passwordHash}, ${input.fullName}, ${input.role})
  `;
}

export async function getStaffRole(id: string): Promise<{ id: string; role: string } | null> {
  const db = sql();
  const [target] = await db`
    SELECT id::text AS id, role FROM avila.app_user WHERE id = ${id}::uuid LIMIT 1
  `;
  return (target as { id: string; role: string } | undefined) ?? null;
}

export async function countOtherActiveSuperAdmins(id: string): Promise<number> {
  const db = sql();
  const [count] = await db`
    SELECT count(*)::int AS n
    FROM avila.app_user
    WHERE role = 'super_admin' AND active = true AND id <> ${id}::uuid
  `;
  return count?.n ?? 0;
}

export async function updateStaffUser(input: {
  id: string;
  role: AppRole;
  active: boolean;
  fullName: string | null;
  passwordHash?: string;
}): Promise<void> {
  const db = sql();
  if (input.passwordHash) {
    await db`
      UPDATE avila.app_user
      SET role = ${input.role},
          active = ${input.active},
          full_name = ${input.fullName},
          password_hash = ${input.passwordHash},
          updated_at = now()
      WHERE id = ${input.id}::uuid
    `;
    return;
  }
  await db`
    UPDATE avila.app_user
    SET role = ${input.role},
        active = ${input.active},
        full_name = ${input.fullName},
        updated_at = now()
    WHERE id = ${input.id}::uuid
  `;
}

export async function deleteStaffSessions(userId: string): Promise<void> {
  const db = sql();
  await db`DELETE FROM avila.app_session WHERE user_id = ${userId}::uuid`;
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const UUID = /^[0-9a-f-]{36}$/i;

export type StaffAccountError = "datos" | "password" | "duplicate" | "self" | "last";

export async function createStaffAccount(input: {
  email: string;
  password: string;
  role: string;
  fullName: string;
}): Promise<StaffAccountError | null> {
  const email = input.email.trim().toLowerCase();
  const fullName = input.fullName.trim().slice(0, 120);
  if (!EMAIL.test(email) || !isAppRole(input.role)) return "datos";
  if (input.password.length < 8 || input.password.length > 200) return "password";
  if (await staffEmailTaken(email)) return "duplicate";
  await insertStaffUser({
    email,
    passwordHash: await hashPassword(input.password),
    fullName: fullName || null,
    role: input.role,
  });
  return null;
}

export async function updateStaffAccount(
  actorId: string,
  input: {
    id: string;
    role: string;
    active: boolean;
    password: string;
    fullName: string;
  },
): Promise<{ error: StaffAccountError } | { error: null; rotateSession: boolean }> {
  const fullName = input.fullName.trim().slice(0, 120);
  if (!UUID.test(input.id) || !isAppRole(input.role)) return { error: "datos" };
  if (input.password && (input.password.length < 8 || input.password.length > 200)) {
    return { error: "password" };
  }
  if (actorId === input.id && !input.active) return { error: "self" };

  const target = await getStaffRole(input.id);
  if (!target) return { error: "datos" };

  const removesSuperAdmin =
    target.role === "super_admin" && (input.role !== "super_admin" || !input.active);
  if (removesSuperAdmin && (await countOtherActiveSuperAdmins(input.id)) < 1) {
    return { error: "last" };
  }

  await updateStaffUser({
    id: input.id,
    role: input.role,
    active: input.active,
    fullName: fullName || null,
    passwordHash: input.password ? await hashPassword(input.password) : undefined,
  });
  if (input.password || !input.active) await deleteStaffSessions(input.id);
  return { error: null, rotateSession: Boolean(input.password) && actorId === input.id };
}
