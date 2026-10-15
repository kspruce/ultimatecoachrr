# Code health check (October 2026)

How this was checked: ruff (lint), bandit (security), radon (complexity), a
read-through of the session/drill/storage/startup code, and running the app
and its migrations against a throwaway local Postgres. Nothing here was
changed as part of the check.

**Overall:** the bones are right: blueprints, SQLAlchemy models, WTForms,
Alembic migrations, team scoping on most queries, CSRF on. Average function
complexity is a "B". The problems are what builds up when you learn as you
go: a few real security leaks, a backup that silently drops tables, and a lot
of copy-paste and leftover cruft. Most of it is quick to fix; nothing needs a
rewrite.

## Fix soon (security)

1. **Admin password in the code.** `run.py` `ensure_admin_exists()` creates
   the admin account with a hard-coded email and password, and it's in git
   history. Change that password now, and make the function read it from an
   environment variable (or delete it now that the admin exists).
2. **`.env` is committed** even though `.gitignore` lists it (it was added
   before the ignore rule). I didn't open it. If it holds real keys, rotate
   them, then `git rm --cached .env` and commit.
3. **`/debug-info` is public** (no login) and is meant to hide the database
   password with `.replace('://:@', ...)`, which never matches, so the full
   `DATABASE_URL` including the password would be returned. It only doesn't
   leak today because the response crashes first (`ALLOWED_EXTENSIONS` is a
   set and can't be turned into JSON). Delete the route.
4. **Third-party script** `sites.super.myninja.ai/...daytona-script.js` is in
   29 templates. In most it sits outside a `{% block %}` and probably never
   renders, but it shouldn't be there; delete those lines.
5. **`SECRET_KEY` falls back to `'dev-secret-key-change-in-production'`.**
   Check that Railway has `SECRET_KEY` set; otherwise anyone can forge
   login cookies.

## Data safety

6. **The JSON ZIP backup silently skips tables with dates.**
   `enhanced_data_manager` only converts `datetime` values, so any row with a
   plain `date` or `time` makes the whole table fail with "Object of type date
   is not JSON serializable". The failure is recorded in the summary file
   inside the ZIP, but the download still succeeds. Confirmed on a test copy
   for `session_plan`. Tables at risk: `session_plan`, `game`, `tournament`,
   `player`, `scouting_report`, `off_season_phases`, `testing_phase`,
   `smart_goals`, `user_session_completions`. **Don't rely on those backups**
   until this is fixed (it's a small fix: also convert `date` and `time` with
   `.isoformat()`).
7. **IDs are assigned as `max(id) + 1` in 29 places** to work around Postgres
   sequences being out of step after the data move. Two people saving at the
   same moment get the same id and one save fails. Reset the sequences once
   (`EnhancedDataManager.reset_sequences()` exists) and let the database
   assign ids again.
8. **Schema changes outside Alembic.** `add_play_image_url.py` runs on every
   boot and `create_app()` also adds `play.image_url`/`play.sort_order` itself;
   Alembic doesn't know these columns exist. Move them into a migration.
   (Separately, `run.py` runs `flask db upgrade` on every boot; that's fine
   but worth knowing: deploying applies migrations.)

## Bugs found along the way

9. **Admin menu crashes when Discord is off.** `base.html` links to
   `discord.settings`, a route that only exists when `DISCORD_ENABLED=true`.
10. `routes/session.py` `rsvp()` uses `AdminSessionRSVPForm`, which isn't
    imported, so that branch raises `NameError`.
11. Session PDF export (`/sessions/<id>/export_pdf`) can't work: neither
    `pdfkit` nor `weasyprint` is installed, and its fallback uses variables
    that are never set. It isn't linked anywhere; the printable page is the
    working route.
12. `/sessions/debug/files` reads `SavedDrill.diagram_url`, which doesn't
    exist, so it always errors. Delete it.
13. The drill library search form (`q`, `skill_level`, `focus_area`) is
    ignored by the `drills()` route.
14. The session list's focus-area dropdown lists every team's focus areas.
15. `error_handlers.py` calls `db.session.remove()` at the end of every
    request. Flask-SQLAlchemy already does this; the extra call also throws
    away unsaved work in any code that briefly opens a request context.
16. `storage.store_file_s3` ignores the filename it's given (moot while S3
    isn't used, but the local fallback serves `/tmp/uploads` files from
    `/static`, so local uploads don't load either).

## Multi-team isolation

17. About 40 lookups fetch rows by id alone (`Model.query.get_or_404(id)`)
    without checking the team, e.g. editing or deleting a fitness metric.
    Harmless while Herd is the only team; if other clubs use the site, their
    admins could reach Herd's rows by guessing ids.

## Tidiness (no rush)

- 325 lint findings: 227 unused imports, repeated imports, imports in the
  middle of files. `ruff check --fix` clears about 260 automatically.
- 246 broad `except Exception` blocks (9 bare `except:`), many of which log
  and carry on, which is how problems like #6 stay hidden.
- Very large files: `routes/stats.py` is 4,600 lines; `process_player_stats`
  has a complexity score of 85 (anything over 20 is hard to change safely).
- Copy-paste: the attendance-grouping block appears 5 times in
  `routes/session.py`; badge colour `if/elif` chains repeat across templates.
- 19 one-off scripts at the repo root (including `db_reset.py`); move the
  ones still needed into `scripts/` and delete the rest.
- 45 `__pycache__` files are committed; `git rm -r --cached` them.
- There were no tests until `tests/test_season_import.py`.
