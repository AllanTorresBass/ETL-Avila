export const SESSION_COOKIE = "avila_session";

export const SESSION_MAX_AGE = 60 * 60 * 24 * 7;

export async function hashSessionToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
