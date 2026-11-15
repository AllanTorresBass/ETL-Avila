# ETL-Avila

Person-centered invoice inventory for Ávila GPS: Neon schema, Vercel Blob page uploads, Next.js staff reader, and public marketing SPA.

**GitHub:** https://github.com/AllanTorresBass/ETL-Avila.git

## Apps

| Path | Role | Deploy |
| --- | --- | --- |
| [`web/`](web/) | Staff invoice reader (Next.js + Clerk + Neon + Blob) | Vercel — set **Root Directory** to `web` |
| [`marketing/`](marketing/) | Public site (WhatsApp-only forms) | Netlify — see `marketing/netlify.toml` |

## Quick start (reader)

```bash
# Secrets in repo-root .env (never commit) and web/.env.local for Clerk
cd web && npm install && npm run dev
```

See [docs/avila-etl-architecture.md](docs/avila-etl-architecture.md).
