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

## Triggering (why it is not GitHub cron)
GitHub's `schedule` event is not punctual. Over Oct-Nov 2026 it fired **4 to 9.5 hours
late every single day** (see the `state: YYYY-MM-DD` commit timestamps), so the brief
landed between 11:43 and 17:51 Athens instead of 08:00.

So the primary trigger is **`repository_dispatch`**, fired by an external scheduler that
*is* punctual (cron-job.org, a Cloudflare Worker cron, anything that can POST):

```
POST https://api.github.com/repos/stamags/cargr-watch/dispatches
Authorization: Bearer <fine-grained PAT with Contents: read & write on this repo>
Accept: application/vnd.github+json
Body: {"event_type":"cargr-brief"}
```

Schedule that for **08:00 Europe/Athens** (pick a timezone-aware scheduler so DST is
handled for you). The GitHub crons (`7 5-7 * * *`) stay on as a fallback net.

## Send window
`cargr_brief.py` only mails inside an Athens-hour window, default **08:00-10:00**:
- before `SEND_FROM_HOUR` -> skip, wait for the next trigger;
- at/after `SEND_UNTIL_HOUR` -> skip the day (a "morning" brief at 17:51 is noise);
- `last_sent == today` -> skip, so duplicate triggers are harmless.

Override via repo variables `SEND_FROM_HOUR` / `SEND_UNTIL_HOUR` (Settings -> Secrets and
variables -> Actions -> Variables). Manual *Run workflow* sets `FORCE=1` and ignores all three.

A skipped day costs nothing: `state.json` is untouched, so the next run diffs against the
same snapshot and still reports everything new.

## Notes
- Email recipient/sender default to env; change `EMAIL_TO` / `EMAIL_FROM` if needed.
- Resend free tier sends only to your signup email until a domain is verified.
