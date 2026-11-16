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

1. Database: Neon (asks for a card) or Supabase (free without one: Project > Connect > "Session pooler" string,
   region Frankfurt; free projects pause after 7 days without use). Copy the connection string.
2. Render: New > Blueprint > this repository; it reads `render.yaml`. Type the secrets it asks for: `DATABASE_URL`
   (Neon), `OVERSEER_EMAIL`, and the portal's own Gmail (`SMTP_*`, an App Password).
3. If Render gives a different address than `PORTAL_URL` in `render.yaml`, change `PORTAL_URL` to it before anyone
   sets up a device.
4. Open the Render log, find "Overseer setup link", open it on your laptop and set it up; then add your phone from
   the phone ("Ask to add this device") and approve it from the laptop.

Recovery (every overseer device lost): Render > the service > Shell, `python manage.py invite <your email>`
(Shell needs a paid plan; on the free plan, remove every overseer device in the database's Neon console or set
`OVERSEER_EMAIL` to a new address and redeploy: a setup link is printed whenever the overseer has no approved device).

## Boxes (Lock 2) and one-click sign-in

A box links itself once `PORTAL_URL` is set in its `.env` (its name there: `BOX_SERIAL`, default the computer's
name). Code: `backend/portal_link.py` (box) and `portal/boxes.py` (portal).

- **Keys.** The box makes its own Ed25519 key on first start (database table `box_link`) and signs every request
  (`X-Box-Serial`, `X-Box-Time`, `X-Box-Signature` over method, path, time and body hash). The portal has its own
  key (table `portal_keys`); the box pins it the first time it registers and ignores any answer signed by another.
  A second box claiming a known serial with another key is refused and the overseer is emailed.
  (Reinstalling the portal with a new database = a new key: clear `box_link` on each box so it registers again.)
- **Joining.** A new box appears on the overseer's home as "New box asking to join". The overseer assigns it to a
  site and ticks the rule sets its licence allows (passkey again). Until then it gets no people and no licence.
- **Every minute** (`PORTAL_CHECKIN_S`) the box checks in with health only: each camera's frames per second, the
  rule set running, disk use, version. Never pictures, incidents or names. The answer brings:
  - the site's people (the company's managers, plus supervisors and viewers linked to this site). They become
    accounts on the box (`users.source = 'portal'`) without a usable password; people the portal drops are
    switched off. Accounts made on the box itself are never touched.
  - a licence signed by the portal: `{serial, plugins, issued, valid_until = +7 days}`, kept in Redis
    (`site:licence`) for the drive loader.
- **Licence.** With `LICENCE_REQUIRED=true` (plugin_loader), a rule drive only runs if the licence names its rule
  set and hasn't run out; otherwise the console says why (no licence / not licensed / ran out). A box that can't
  reach the portal keeps its rules for 7 days from its last good check-in. Fixed mode (`PLUGIN_SOURCE=fixed`, the
  graduation Jetson) doesn't check licences.
- **Silent boxes.** 10 minutes without a check-in: logged, and the overseer and that company's managers are
  emailed (once, until it's back).
- **Open console.** Managers, supervisors and viewers see "Open console" next to their site. The portal signs a
  token for that box only (60 s, one use) and the box's `/auth/portal` signs them in. The overseer has no such
  button and the portal refuses them: footage stays with the client. The console's own sign-in page offers
  "Sign in through the SiteSentry portal" when the box is linked.

## What a box reports, and "confirm it's you"

- **Events** (`backend/box_events.py`): rules switched or changed, zones redrawn, accounts added or changed,
  someone added to / removed from face recognition (never who), failed console sign-ins, rule drives accepted or
  refused. Queued in Redis, sent with the next check-in, and written into the portal's chained security log as
  "<company>, <site>: <sentence>". Failed sign-ins and refused drives are also emailed to the overseer. A malformed
  event is skipped, never the whole check-in.
- **Confirm it's you** (`backend/confirm.py`, on when the box is linked; `CONFIRM_CHANGES=auto|on|off`): switching
  rules, timings, zones, accounts, face photos and the summary time answer 428 until the person has confirmed in
  the last 5 minutes. Portal accounts confirm on the portal with their passkey (`/confirm?box=...&back=...`, which
  sends them back with a one-use token); accounts made on the box re-type their password. The console asks in a
  window and repeats the change by itself after a password.
  On the Jetson the box reaches the portal by an internal name, so `PORTAL_PUBLIC_URL` is what browsers open.

## Not yet

Closing the public console door (only once every client signs in through the portal), Arabic security-log
sentences (the log is written in English), portal email (needs its Gmail app password).
