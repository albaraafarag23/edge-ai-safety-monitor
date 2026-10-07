# Going public (free)

Two free pieces:

| Part | Where | Address | Online |
|---|---|---|---|
| Product page | Cloudflare Pages | `https://edge-ai-safety.pages.dev` | Always |
| Console (sign-in, cameras, alerts) | This machine, through Tailscale Funnel | `https://sitesentry.<tailnet>.ts.net` | While this machine and Docker run |

The product page checks `<console>/api/health` and shows **Live demo online / offline**, so visitors
aren't sent to a dead link. Only port 3000 (the website) is published through the tunnel; the
database, Redis and the API are bound to `127.0.0.1` in `docker-compose.yml`.

## Before the link is public

In `.env` (see `.env.example`):
- `AUTH_SECRET`: a long random value, otherwise everyone is signed out when the backend restarts
- `COOKIE_SECURE=true` (the tunnel is HTTPS; browsers also accept it on http://localhost)
- `INTERNAL_API_TOKEN`: a random value (shared by backend and ai_reporting)
- A strong admin password. Change it in the console under **Account**.

Then `docker compose up -d --build`. Containers restart on their own after a reboot
(`restart: unless-stopped`) as long as Docker starts at boot (`sudo systemctl enable docker`).

Give examiners a **viewer** account (read-only) from **Users** in the console.

## 1. Console: Tailscale Funnel (once)

    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up --hostname=sitesentry        # opens a sign-in link (free account)
    sudo tailscale funnel --bg 3000

The first `funnel` prints a link to enable HTTPS and Funnel for your tailnet; open it, approve, and
run the command again. It prints the public address, e.g. `https://sitesentry.tail1234.ts.net`.
`--bg` keeps it on across reboots. Check with `tailscale funnel status`; stop with
`sudo tailscale funnel --https=443 off`.

## 2. Product page: Cloudflare Pages

    npx wrangler@4 login                                           # once, opens the browser (free account)
    scripts/deploy-site.sh https://sitesentry.tail1234.ts.net      # build + publish

It publishes to `https://edge-ai-safety.pages.dev` (Cloudflare adds a suffix if the name
is taken). Run the script again after changing the product page.

## Notes
- Test mode (`CV_TEST_MODE=true`) creates a few incidents a minute, all day. Fine for a demo, but the
  database grows and, with SMTP set, supervisors get emails (repeats are held back by `NOTIFY_COOLDOWN_S`).
- Failed sign-ins are limited: 5 per email and 20 per address in 15 minutes (in memory, reset on restart).
- Screenshots on the product page are in `frontend/public/screenshots/`, captured from the console in test mode.
