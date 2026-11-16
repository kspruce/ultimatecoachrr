# Security review (October 2026)

A pass over the whole app before opening it to more teams or charging for
access. The test suite was green (172 tests) at the start.

## How it was checked

- A cross-team probe: team A with a recorded season, team B's admin logged
  in, every GET page requested with team A's ids. Only one page showed team
  A's data (the scouting filter dropdown, fixed below). Page-level team
  isolation is in good shape.
- Every route that changes data listed with its login and role checks, and
  the ones without a role decorator read by hand.
- Every place templates print unescaped HTML (`|safe`, `|markdown`,
  `Markup`) traced back to who can write that text.
- Config, cookies, headers, uploads, password resets, the login redirect,
  secrets in git history and the pinned dependency versions.

## Fixed in this change

`tests/test_security.py` covers each of these. Every test there fails on the
old code.

| Issue | Who could exploit it | Fix |
|---|---|---|
| Player goals went through `nl2br\|safe` without escaping, so a player could put a script in their goals and it ran for coaches and admins viewing their page | Any player | `nl2br` escapes the text first |
| `\|markdown` let raw HTML through, including `<script>`, `onerror=` and `javascript:` links (drills, sessions, plays, season plan, theory) | Any coach, against their team, admins and the site superadmin | Markdown output is cleaned with `nh3` |
| Ultiplay embed code was printed as raw HTML | Any coach | New `embed_html` filter keeps only https iframes |
| Chart data (`json.dumps` + `\|safe`) could break out of `<script>` through an opponent, player or session name | Anyone who names things | `htmlsafe_json_dumps` / `tojson` |
| Player stats printed a Python list into JS (`None`/`True` aren't JS), so the charts broke on throws without a type | Bug | `tojson` |
| `POST /points/delete/<id>` had no role check: a player could delete points and all their events | Any player | Stat taker or above |
| `/games/add` and `/games/add_multiple` had no role check | Any player | Stat taker or above (stat takers add games from Game Day) |
| `/sessions/<id>/quick_checkin` let anyone set any player's RSVP, with no check that the session or player was on their team | Any player | Admin only (same as the admin RSVP page it's used from), session and player must be this team's |
| Scouting filter, scouting report, session component (plays) and session filter (focus areas) dropdowns listed every team's rows | Any member | Filtered to the current team |
| Login `?next=/\evil.com` redirected off-site | Phishing | Only same-site paths |
| No `Secure`/`SameSite` on login cookies, no security headers | Network attacker / clickjacking | Secure, HttpOnly, SameSite=Lax cookies; `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS |

`SESSION_COOKIE_SECURE=0` is needed to log in over plain http locally
(it's off automatically with `FLASK_DEBUG=1`).

## Second round

Also covered by tests (`tests/test_security.py`, `tests/test_accounts.py`).

| Change | Why |
|---|---|
| Updated Flask, Werkzeug, Jinja2, Pillow, requests, sqlparse, Mako, Markdown, python-dotenv, idna, zipp (and blinker, itsdangerous for Flask 3.1); CI runs `pip-audit` | All had published vulnerabilities; CI now fails on new ones |
| PDF exports only fetch http(s) URLs on public addresses | The server-side browser could otherwise be pointed at cloud metadata or internal services from a coach's text |
| gunicorn runs 8 threads in one process | One slow export or backup no longer stalls everyone. It must stay one process: the stats cache, rate limits, playbook export progress and the Discord bot live in its memory |
| Logins carry a fingerprint of the password hash | Changing a password, or using a reset link, signs out every other device and remember-me cookie. Everyone logs in once more after this deploys |
| Common passwords refused at sign-up and password change | The first guesses an attacker tries |
| Logout is a POST (exempt from CSRF, so an old page can still log out) | Other sites could log people out with a link |
| CSP: the safe parts enforced, the full policy report-only, violations logged by `/csp-report` | A crawl of every page in Chromium found no violations. Watch the logs for `CSP would block`; when they're quiet, merge `CSP_REPORT_ONLY` into `CSP` in `app/__init__.py` |
| Share tokens compared in constant time; unused annotation forms that listed every team's users deleted | Small leftovers |
| Form tokens last as long as the login, and an expired form shows a page instead of raw JSON | Pages left open for over an hour (e.g. at a tournament) couldn't save |
| Optional Sentry error reports (`SENTRY_DSN`), without personal data | You find out about errors before customers tell you |

## Third round

| Change | Notes |
|---|---|
| Site backups fixed and tested | A test fills two teams, backs up through both export buttons, changes the data, restores through both restore buttons with "clear existing" and compares every row of every table, on SQLite and Postgres. It found four bugs, now fixed: the table order was backwards (on Postgres "clear existing" silently left newer data behind), link tables were doubled, the restoring superadmin's own account wasn't restored, and "Import data" didn't reset Postgres id counters (every new row then failed) |
| Team admins: Team settings -> Your data | Download everything the team holds (CSV and JSON, no passwords, secrets or live invite links), or delete the team (team name + password; emails the site owner). `app/utils/team_data.py` decides which rows are a team's; tests check the other team is never included or touched |
| Two-step sign-in for superadmins | Authenticator app codes, 10 hashed recovery codes, single-use codes, `flask reset-two-factor <username>` for a lost phone. Optional for now (Account Settings); **switch on "Require it" under Manage Teams -> Team sign-ups before sharing the site** |
| Privacy policy at /privacy | Linked from the footer and sign-up pages. Set `SITE_OPERATOR`, `PRIVACY_CONTACT_EMAIL` and `BACKUP_RETENTION_DAYS`; services are listed only when they're switched on |
| "Remember me" lasts 30 days | Was Flask-Login's default of a year |

## Fourth round (November 2026)

A pass over what the first reviews didn't cover and what's been added
since: season plans, programmes and starter programmes, the drill library
and editor, Ask leaders, the Leadership hub and handbook, Discord buttons,
clip sharing, PDF exports and onboarding. The suite was green at the start
(834 passed, 20 skipped).

**How it was checked**

- A write probe. Two fully used teams (`tests/rich_data.py`, every feature
  switched on). Every route that changes data (about 290) was posted to by
  Alpha's plain player with Alpha's ids, then by Bravo's team admin with
  Alpha's ids, and the whole database was compared before and after each
  request. The only changes were the ones players are meant to make
  (answering RSVPs, asking the leaders, their own onboarding and calendar
  link).
- A read probe. Bravo's admin opened every page and JSON endpoint with
  Alpha's ids. None showed any of Alpha's data. (As a check that the probe
  works, Alpha's own player saw Alpha's data on 66 of them.)
- Every write route without a role decorator read by hand: playbook,
  theory, programmes, season plans, handbook, Leadership hub, Ask leaders,
  fitness, goals.
- Every place text reaches the page unescaped: `|safe`, `Markup`,
  `innerHTML` and d3's `.html()` in templates and scripts, names inside
  inline `onsubmit`/`oninput` handlers, and stored links printed in `href`.
- Uploads, share links, Discord, the sign-in flows, requests the server
  makes, CSRF, config and dependencies.

**Fixed**

| Issue | Who could exploit it | Fix |
|---|---|---|
| Clip annotation notes (rich text from the editor) were printed with `\|safe`, and the edit page loaded them into the editor as HTML, so a note could run script | Any player, against coaches and admins who open the clip or edit the note | Notes are cleaned with `nh3` when saved and when loaded for editing; the clip page also cleans notes saved before this (`rich_text` filter) |
| The password reset email built its link from the request's host, and `ProxyFix` trusts `X-Forwarded-Host`, so a forged header could put a working reset token in a link to another site | Anyone who knows a username or email, if the host's proxy passes that header through (couldn't be checked from here) | The emailed link uses `BASE_URL`, like the site's other emails |
| Game Day put player names into `innerHTML` (line chips, substitution picker, save-line dialog) | A coach, against the captains and admins recording a game | Names are escaped first |
| The pass-network tooltips on a game's stats page used player names as HTML | A coach, against anyone on the team who hovers | Names are escaped first |
| Names inside inline handlers: the browser decodes `&#39;` back to `'` before running the handler, so a name could end the string. The team name in Manage Teams' delete box, squad names and session template names | A team admin or anyone signing up a new club, against the superadmin; a coach, against admins | Passed as JSON strings (`\|tojson\|forceescape`) |
| `/sessions/<id>/components` listed a session's blocks before the coaches had shared the plan | Any player on the team | Same check as the detail page and PDF |
| Game video links: WTForms' `URL()` accepts `javascript://host/%0a...`, and adding several games at once didn't check links at all | A stat taker or coach. The links open in a new tab, which stops Chromium running them, so this is a safety net | Only http(s) links are kept |

Tests: `tests/test_clips.py`, `tests/test_accounts.py`,
`tests/test_training.py`, `tests/test_security.py`, and
`tests/test_point_detail_browser.py` for the two in-browser fixes (they
run in CI, which installs Chromium). Each fails on the old code.

**Left to decide**

1. ~~**Players can claim any unlinked player profile on their team**~~
   **Decided and done:** picking a profile on `/auth/link_player` now sends
   a request that a coach approves or declines (Users page, and the home
   page's "Needs attention", so it's in the coach summary email too).
   Coaches and above still link their own account directly, and invite
   links work as before. Tests in `tests/test_teams.py`.
2. **Spreadsheet formulas in CSV exports.** Annotation titles and other
   text people type go into CSV exports as they are, so a cell starting
   with `=` runs as a formula when a coach opens the file in Excel. Putting
   a `'` in front of such cells would stop it, but changes what the export
   holds.
3. **The script part of the Content-Security-Policy is still report-only.**
   Enforcing it would have blunted several of the issues above. Inline
   scripts and handlers need `'unsafe-inline'` for now; moving them into
   files would let the policy block injected script.

## Still to do before selling access

1. **Check Railway's database backups.** These are set on the Postgres
   service's Backups tab in Railway (a paid-plan feature), not in this code,
   so I couldn't check them from here. Turn on scheduled
   backups, set `BACKUP_RETENTION_DAYS` to match how long they're kept, and
   occasionally restore one into a spare database to check it. The site's own
   JSON backup (Data management) is a second copy you can download.
2. **Have the privacy policy reviewed** by someone who knows data protection
   law where you operate, and add terms of service before charging.
3. **Billing** (on hold): use a hosted checkout such as Stripe Checkout.
4. **Rate limits across restarts**: set `RATELIMIT_STORAGE_URI` to Redis if
   you add one.
5. **Check `BASE_URL` in Railway's Variables is the live site's address.**
   Password reset emails now take their links from it (as Discord posts
   and the other emails already did). Without it they use the old default
   in `config.py`.

## Checked and fine

- Page-level team isolation (see the probe above), superadmin-only backup,
  import and export routes, role checks on user management (no one can grant
  a role above their own or touch a superadmin).
- Password reset tokens are signed, time-limited and single-use.
- CSRF protection is on globally; the secret key has no hard-coded fallback.
- The `.env` once committed to git history held only placeholder values. If
  production ever ran with `SECRET_KEY=your...`, rotate it.
- Drill diagram images are served with a sandboxing CSP and unguessable names.
