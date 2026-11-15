import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

function applyEnvFile(path: string) {
  if (!existsSync(/*turbopackIgnore: true*/ path)) return false;
  const text = readFileSync(/*turbopackIgnore: true*/ path, "utf8");
  let applied = false;
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const idx = trimmed.indexOf("=");
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    // Skip blank assignments so empty web/.env.local does not block ../.env.
    if (!value) continue;
    if (!process.env[key]) {
      process.env[key] = value;
      applied = true;
    }
  }
  return applied;
}

/** Load repo-root .env into process.env for local Next.js (server only). */
export function ensureEnv() {
  if (process.env.DATABASE_URL || process.env.DATABASE_URL_UNPOOLED) return;

  const roots = [process.cwd(), join(/*turbopackIgnore: true*/ process.cwd(), "..")];
  for (const root of roots) {
    for (const name of [".env.local", ".env"]) {
      applyEnvFile(join(/*turbopackIgnore: true*/ root, name));
    }
  }
}
