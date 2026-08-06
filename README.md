# car.gr Morning Brief

Daily cloud email (08:00 Europe/Athens) of **new listings** and **price changes** for
saved car.gr searches, with first-photo thumbnails. Runs on **GitHub Actions** — no PC
needed. State (yesterday's snapshot) lives in `state.json`, committed back each run.

## How it works
1. `cargr_brief.py` fetches each search via **ZenRows** (`js_render`, `wait=12000`
   because car.gr renders client-side), parses listings, diffs against `state.json`.
2. Emails an HTML brief via **Resend** (new listings 🆕, price changes 🔻/🔺, full table).
3. Rewrites `state.json`; the workflow commits it so tomorrow can diff.

## Configure
- **Secrets** (Settings → Secrets and variables → Actions): `ZENROWS_KEY`, `RESEND_KEY`.
- **Add a search**: edit the `SEARCHES` list in `cargr_brief.py` (name + car.gr URL), commit.
- **Run now / baseline**: Actions tab → *car.gr Morning Brief* → *Run workflow*.

## Notes
- Schedule uses two crons (05:00 & 06:00 UTC) gated to Athens-08:00 so DST stays correct.
- Email recipient/sender default to env; change `EMAIL_TO` / `EMAIL_FROM` if needed.
- Resend free tier sends only to your signup email until a domain is verified.
