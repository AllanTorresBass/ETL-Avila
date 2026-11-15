# Ávila GPS invoice reader

Next.js + shadcn UI for browsing people, invoices, and page-level documents loaded into Neon (`avila` schema) and Vercel Blob. Staff-only: Clerk auth + Vercel Deployment Protection.

```bash
# From repo root, with DATABASE_URL, BLOB_*, and Clerk keys in ../.env
cd web
cp .env.example .env.local   # or symlink ../.env
npm install
npm run dev
```

## Auth

- `proxy.ts` runs `clerkMiddleware` and `auth.protect()` on all routes except `/sign-in` and `/sign-up`.
- Optional `CLERK_ALLOWED_EMAILS` (comma-separated) restricts API blob access to listed staff.
- Vercel project `etl-avila` uses SSO Deployment Protection on all deployments.

## Blob

- UI previews go through `/api/blob/[documentId]` (never raw backup paths).
- Private stores: `BLOB_ACCESS=private` + `@vercel/blob` `get(pathname, { access: 'private' })`.
- Legacy public stores still work via `blob_url` fetch fallback.

See [docs/avila-etl-architecture.md](../docs/avila-etl-architecture.md).
