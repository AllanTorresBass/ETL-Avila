---
name: avila-gps-ui
description: Documents or builds Ávila GPS screens using the brand, card and directory display models, and WhatsApp-only visitor data handling. Use when working on Ávila GPS UI, branding, cards, carousels, the doctor directory, contact or appointment forms, empty states, or how patient name, phone, or cédula is shown or sent.
---

# Ávila GPS UI

Read [avila-gps-ui-display-standards.md](../../../avila-gps-ui-display-standards.md) before writing or changing a screen. That file is the inventory. The rules in `.cursor/rules/avila-brand.mdc`, `avila-data-display.mdc`, and `avila-visitor-data.mdc` are the constraints.

## Workflow

1. Name the route: `/`, `/nosotros`, `/servicios`, `/equipo-medico`, or `/contacto`.
2. Pick the display model from section 4 of the standards doc. Use cards, chips, or the carousel. Add a table only when the data is a true column grid.
3. Apply the brand tokens: Montserrat, navy `#0A2A6B`, green `#6CC24A` to `#0F7A33`, pills for actions, `rounded-3xl` cards, glass header over photos.
4. If the screen collects a name, phone, cédula, email, date, or message, keep it in component state and send it only through `https://wa.me/584121716058`.
5. Check the edge cases below before finishing.

## Edge-case check

- A directory with no matches shows “No se encontraron médicos” and tells the visitor to change the search or the filter.
- A fresh load of `/servicios`, `/nosotros`, `/equipo-medico`, or `/contacto` 404s on Netlify until the host rewrites those paths to `index.html`.
- Appointment requires service, patient name, and phone. Cédula, date, and specialist stay optional.
- Contact requires name, phone, and message. Email stays optional.
- Submit opens WhatsApp. It does not write visitor fields to storage or another API.
- Telemedicine copy must not mix 12 h/7 and 24/7 on the same new screen. The live site already uses both. Match the screen you are editing, and do not spread the other figure.
- A published stat such as “45+” is not the directory length. The directory length is 48. Label which one the screen shows.
