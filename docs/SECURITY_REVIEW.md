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

## Still to do before selling access

Roughly in priority order.

1. **Update pinned dependencies.** Several have published CVEs:
   Pillow 10.0.0 (fixed in 10.3+), Jinja2 3.1.3 (3.1.6), Werkzeug 3.0.2
   (3.0.6+) and requests 2.31.0 (2.32.4). Run
   `pip-audit -r requirements.txt` and add it to CI.
2. **PDF export renders user content in Chromium on the server.** Markdown is
   now cleaned, but Playwright will still fetch any `<img src>` in the page,
   including internal addresses. In `app/utils/pdf.py`, block network
   requests (`page.route('**/*', ...)` allowing only `data:` URLs) since
   images are already inlined.
3. **One gunicorn worker.** `Procfile`/`railway.toml` start gunicorn with the
   default single sync worker and a 300s timeout, so one slow PDF export or
   backup stalls the site for everyone. Use `--workers 2-4` (or
   `--worker-class gthread --threads 4`), and move rate-limit storage to Redis
   (`RATELIMIT_STORAGE_URI`) so limits hold across workers.
4. **Logging out other sessions.** Changing a password doesn't sign out
   other devices or remember-me cookies (Flask-Login uses the plain user id).
   Add a per-user session token used as `get_id()`, rotate it on password
   change, and set `login.session_protection = 'strong'`.
5. **Logout is a GET.** Any site can log a user out with an `<img>` tag.
   Make `/auth/logout` POST-only (the guest write-block already allows it).
6. **Content-Security-Policy.** The headers above stop framing; a CSP is the
   next layer against XSS. The templates use a lot of inline `<script>` and
   CDN scripts, so start with `Content-Security-Policy-Report-Only` and
   tighten it.
7. **Password policy.** Only an 8-character minimum. Consider rejecting
   common/breached passwords and offering 2FA for admin and superadmin
   accounts. The superadmin can see every team; protect it hardest.
8. **Players' data on public share links.** `/sessions/<id>/guest/<token>`
   shows the attendance list (player names) to anyone with the link. Check
   that's intended; consider expiring links (`share_token_expires` already
   exists but is never set). Compare tokens with `hmac.compare_digest`.
9. **Dead code that leaks across teams if reused.** `app/forms/annotation_forms.py`
   and `AnnotationFilterForm` in `app/forms/annotation.py` list every team's
   users and players. Nothing imports them today; delete them.
10. **Fitness metrics.** Some fitness pages load a metric by id without a
    team check. Metrics can be shared on purpose, and the records shown are
    filtered by team, so only another team's metric name can show. Use
    `_team_metric_or_404` everywhere for consistency.
11. **Legal and commercial basics before charging:** a privacy policy and
    terms (you store minors' names and fitness/attendance data, possibly
    under GDPR), a way for a team to export and delete its data, offsite
    database backups with a tested restore, error monitoring (e.g. Sentry),
    and billing through a hosted checkout (Stripe Checkout and its customer
    portal) so card details never touch this app.

## Checked and fine

- Page-level team isolation (see the probe above), superadmin-only backup,
  import and export routes, role checks on user management (no one can grant
  a role above their own or touch a superadmin).
- Password reset tokens are signed, time-limited and single-use.
- CSRF protection is on globally; the secret key has no hard-coded fallback.
- The `.env` once committed to git history held only placeholder values. If
  production ever ran with `SECRET_KEY=your...`, rotate it.
- Drill diagram images are served with a sandboxing CSP and unguessable names.
