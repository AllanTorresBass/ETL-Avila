import { isAppRole, type AppRole } from "@/lib/access";

export type SessionUser = {
  id: string;
  email: string;
  fullName: string | null;
  role: AppRole;
};

/** Tagged-template client from Neon or `sql()`. */
type SqlClient = (
  strings: TemplateStringsArray,
  ...values: unknown[]
) => PromiseLike<Array<Record<string, unknown>>>;

export async function userFromTokenHash(db: SqlClient, tokenHash: string): Promise<SessionUser | null> {
  const rows = await db`
    SELECT u.id::text AS id, u.email, u.full_name, u.role
    FROM avila.app_session s
    JOIN avila.app_user u ON u.id = s.user_id
    WHERE s.token_hash = ${tokenHash}
      AND s.expires_at > now()
      AND u.active = true
    LIMIT 1
  `;
  const row = rows[0];
  if (!row || !isAppRole(row.role)) return null;
  const id = row.id;
  const email = row.email;
  if (typeof id !== "string" || typeof email !== "string") return null;
  return {
    id,
    email,
    fullName: typeof row.full_name === "string" ? row.full_name : null,
    role: row.role,
  };
}
