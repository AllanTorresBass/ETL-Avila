import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { sql } from "@/lib/db";
import { userFromTokenHash, type SessionUser } from "@/lib/session-db";
import { hashSessionToken, SESSION_COOKIE, SESSION_MAX_AGE } from "@/lib/session-token";

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}

export async function getCurrentUser(): Promise<SessionUser | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return userFromTokenHash(sql(), await hashSessionToken(token));
}

export async function createSession(userId: string): Promise<void> {
  const token = randomBytes(32).toString("base64url");
  const db = sql();
  await db`
    INSERT INTO avila.app_session (user_id, token_hash, expires_at)
    VALUES (${userId}::uuid, ${await hashSessionToken(token)}, now() + interval '7 days')
  `;
  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, cookieOptions(SESSION_MAX_AGE));
}

export async function destroySession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (token) {
    const db = sql();
    await db`DELETE FROM avila.app_session WHERE token_hash = ${await hashSessionToken(token)}`;
  }
  jar.set(SESSION_COOKIE, "", cookieOptions(0));
}
