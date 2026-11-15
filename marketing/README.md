# Ávila GPS marketing site

Public Spanish SPA (React Router + Tailwind + Framer Motion). Visitor fields stay in React state and leave only through WhatsApp (`wa.me/584121716058`).

```bash
cd marketing
npm install
npm run dev
```

Deploy on Netlify. [`netlify.toml`](netlify.toml) rewrites all paths to `index.html` so deep links (`/servicios`, `/contacto`, …) work on cold load.

See [../avila-gps-ui-display-standards.md](../avila-gps-ui-display-standards.md).
