/**
 * Create or reset bootstrap staff accounts.
 *
 * AUTH_BOOTSTRAP_USERS=email|password|role|name;email|password|role|name
 * Roles: super_admin, revisor, lector.
 * Re-running replaces the password hash for those emails.
 *
 * Usage: node scripts/seed_app_users.mjs
 */
import { randomBytes, scrypt } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const scryptAsync = promisify(scrypt);
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const { neon } = createRequire(join(root, "web/package.json"))("@neondatabase/serverless");

function loadEnv(path) {
  let text = "";
  try {
    text = readFileSync(path, "utf8");
  } catch {
    return;
  }
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
    if (value && !process.env[key]) process.env[key] = value;
  }
}

async function hashPassword(password) {
  const salt = randomBytes(16);
  const hash = await scryptAsync(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$16384$8$1$${salt.toString("base64url")}$${hash.toString("base64url")}`;
}

loadEnv(join(root, ".env"));
loadEnv(join(root, "web/.env.local"));

const raw = process.env.AUTH_BOOTSTRAP_USERS || "";
const url = process.env.DATABASE_URL_UNPOOLED || process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL_UNPOOLED is missing");
  process.exit(1);
}
if (!raw.trim()) {
  console.error("AUTH_BOOTSTRAP_USERS is missing");
  process.exit(1);
}

const accounts = raw
  .split(";")
  .map((part) => part.trim())
  .filter(Boolean)
  .map((part) => {
    const [email, password, role, name] = part.split("|").map((item) => item.trim());
    return { email: email.toLowerCase(), password, role, name: name || null };
  });

const allowed = new Set(["super_admin", "revisor", "lector"]);
for (const account of accounts) {
  if (!account.email.includes("@") || !account.password || !allowed.has(account.role)) {
    console.error("Each account needs email|password|role|name");
    process.exit(1);
  }
}

const sql = neon(url);
const schema = readFileSync(join(root, "sql/007_app_access.sql"), "utf8");
const statements = schema
  .split(";")
  .map((statement) => statement.replace(/--.*$/gm, "").trim())
  .filter(Boolean);

for (const statement of statements) {
  await sql.query(statement);
}

for (const account of accounts) {
  const passwordHash = await hashPassword(account.password);
  await sql`
    INSERT INTO avila.app_user (email, password_hash, full_name, role)
    VALUES (${account.email}, ${passwordHash}, ${account.name}, ${account.role})
    ON CONFLICT (email) DO UPDATE
      SET password_hash = EXCLUDED.password_hash,
          role = EXCLUDED.role,
          full_name = COALESCE(avila.app_user.full_name, EXCLUDED.full_name),
          active = true,
          updated_at = now()
  `;
  console.log(`${account.email} ${account.role}`);
}
