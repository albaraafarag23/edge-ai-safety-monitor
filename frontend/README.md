# Dashboard

React + TypeScript + Vite + Tailwind. Data comes from the backend API, and live updates
arrive over Server-Sent Events (`/api/events`).

## Run in development
Start the backend (and the rest of the stack) with Docker, then run the dashboard with hot reload:

    docker compose up -d
    cd frontend
    npm install
    npm run dev          # http://localhost:3000, /api is proxied to http://localhost:8000

Set `BACKEND_URL` to proxy to another backend.

## Check before committing
    npm run typecheck
    npm test
    npm run build

## In Docker
`docker compose up -d --build frontend` serves the built app with nginx on http://localhost:3000.
nginx also proxies `/api` to the backend, so the browser only ever talks to one origin.

## Structure
| Path | What's there |
|---|---|
| `src/api/` | Types (mirroring `docs/contracts.md`), fetch client, TanStack Query hooks |
| `src/lib/live.tsx` | Live connection: invalidates cached data on new incidents, reports and status changes; toasts for HIGH/CRITICAL |
| `src/lib/format.ts` | Formatting helpers and severity/status colours (tested in `format.test.ts`) |
| `src/components/` | Layout, incident table, shared UI pieces |
| `src/pages/` | Overview, Incidents (filters in the URL), Incident detail (evidence, AI report, status workflow) |

## Next steps
- Login and roles (supervisor / admin)
- Analytics page (trends, compliance rate, worst zones and hours)
- Zone editor: draw zones on a camera frame and save them to the plugin
- Settings: supervisor emails, cooldown
