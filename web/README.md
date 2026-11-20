# Ávila GPS invoice reader

Next.js + shadcn UI for browsing people, invoices, and page-level documents loaded into Neon (`avila` schema) and Vercel Blob. Staff-only: email and password plus a role, and Vercel Deployment Protection.

```bash
# From repo root, with DATABASE_URL and BLOB_* in ../.env
cd web
cp .env.example .env.local   # or symlink ../.env
npm install
npm run dev
```

## Auth

- Apply `sql/007_app_access.sql`, then seed accounts with `AUTH_BOOTSTRAP_USERS` (see `.env.example`) and `node scripts/seed_app_users.mjs`.
- `proxy.ts` requires a session cookie on every route except `/sign-in`.
- Roles: `super_admin` (lectura, revisión y cuentas), `revisor` (lectura y revisión), `lector` (solo lectura).
- Super admins create the other accounts at `/usuarios`.
- Vercel project `etl-avila` uses SSO Deployment Protection on all deployments.

## Blob

- UI previews go through `/api/blob/[documentId]` (never raw backup paths).
- Private stores: `BLOB_ACCESS=private` + `@vercel/blob` `get(pathname, { access: 'private' })`.
- Legacy public stores still work via `blob_url` fetch fallback.

See [docs/avila-etl-architecture.md](../docs/avila-etl-architecture.md).
