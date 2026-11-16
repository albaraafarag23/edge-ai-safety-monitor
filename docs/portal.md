# The SiteSentry portal

One web address for everyone: the overseer (SiteSentry) sees every client company, site, person and box; each
client's people sign in here and (from step 3) go straight to their own site's box. Footage, incidents, reports and
face photos never come here: they stay on each site's box.

Code: `portal/` (FastAPI server, `main.py`) + `frontend/src/portal/` (screens, same look as the console, English and
Arabic). Hosting: Render (free web service, `render.yaml`) + Neon (free Postgres).

## Who can do what

| | Overseer | Manager | Supervisor / viewer |
|---|---|---|---|
| Companies | add, suspend (signs everyone out) | sees their own | sees their own sites |
| Sites | add | add to their company | - |
| People | add anyone, incl. managers | add supervisors and viewers | - |
| New devices | approves managers' (and anyone's) | approves their staff's | asks |
| Security log | everything + chain check | their company | - |

## Signing in: passkeys only (Lock 1)

- No passwords. A passkey is made by the phone or laptop (fingerprint, face, Windows Hello, screen lock) and never
  leaves it; it only works on the portal's own address (`PORTAL_URL`), which stops phishing. **Changing
  `PORTAL_URL` later means everyone sets up their devices again.**
- First device: a one-time invite link (72 h) from whoever added you; that device is approved at once.
- Any later device: "Ask to add this device" on the sign-in page; it waits until an approver says yes (they get an
  email). Unknown emails get the same answer, so nobody can find out who has an account.
- Dangerous changes (people, sites, companies, approving or removing devices) ask for the passkey again when the
  last check is over 5 minutes old.
- Every overseer sign-in emails the overseer.
- Removing a device, switching a person off or suspending a company signs them out at once (sessions live in the
  database).

## The security log

Every sign-in, approval and change. Each entry includes the hash of the one before, so editing or deleting an old
entry breaks the chain from there; the overseer's log page checks it every time it opens.

## Running it

Locally (SQLite, no setup):

    cd frontend && npm run build:portal
    cd ../portal && pip install -r requirements.txt
    OVERSEER_EMAIL=you@example.com PORTAL_UI_DIR=../frontend/dist-portal uvicorn main:app --port 8010

The first start prints the overseer's one-time setup link. Open it on http://localhost:8010 (passkeys need
`localhost` or HTTPS). Screens with live reload: `npm run dev:portal` (port 3010) with `PORTAL_URL=http://localhost:3010`
for the server.

Tests: `cd portal && python -m pytest -q test_portal.py` (a software passkey; also part of `scripts/check-all.sh`).

## Putting it online (Render + Neon, free)

1. Neon: create a project (region Frankfurt), copy the connection string.
2. Render: New > Blueprint > this repository; it reads `render.yaml`. Type the secrets it asks for: `DATABASE_URL`
   (Neon), `OVERSEER_EMAIL`, and the portal's own Gmail (`SMTP_*`, an App Password).
3. If Render gives a different address than `PORTAL_URL` in `render.yaml`, change `PORTAL_URL` to it before anyone
   sets up a device.
4. Open the Render log, find "Overseer setup link", open it on your laptop and set it up; then add your phone from
   the phone ("Ask to add this device") and approve it from the laptop.

Recovery (every overseer device lost): Render > the service > Shell, `python manage.py invite <your email>`
(Shell needs a paid plan; on the free plan, remove every overseer device in the database's Neon console or set
`OVERSEER_EMAIL` to a new address and redeploy: a setup link is printed whenever the overseer has no approved device).

## Not yet (step 3 and later)

Boxes registering and checking in (health every minute, approval, licence for rule drives), one-click sign-in from
the portal to a site's box, alerts for silent boxes, Arabic security-log sentences (the log is written in English).
