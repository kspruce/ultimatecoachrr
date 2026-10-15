# Code health (updated October 2026)

Checked with ruff, bandit, radon, a read-through, and by running the app and
its migrations against a local Postgres. The test suite (`tests/`) runs on
SQLite and Postgres in GitHub Actions on every pull request.

## Still to do

**You need to do these yourself**
1. **Change the admin password.** The old one is still in git history (and
   so are the seed passwords that were in `db_manager.py`).
2. **`.env` is committed.** `config.py` loads it at startup, so the live site
   may read settings from it. Copy what it needs into Railway's Variables
   (especially `SECRET_KEY`), change any real keys in it, then
   `git rm --cached .env`.

**Code**
3. **Duplicate URLs.** `main` and `data_management` both define the six
   `/admin/export-data`, `/admin/import-data`, ... routes, and `calendar` and
   `session` both define `/sessions/<id>/rsvp`. The first blueprint registered
   wins silently, so the other copy is dead code. Pick one of each and delete
   the other.
4. **Fitness goals are half-built.** There's no `FitnessGoal` model, so the
   goal code paths fall back to "not implemented", and the "Set New Goal" page
   has no template (its button is hidden for now).
5. **Session PDF export** (`/sessions/<id>/export_pdf`) can't work: neither
   `pdfkit` nor `weasyprint` is installed. It isn't linked anywhere; the
   printable page is the working route.
6. `routes/session.py` `drills()` ignores the drill library's search form.
7. The session list's focus-area dropdown lists every team's focus areas.
8. `error_handlers.py` calls `db.session.remove()` after every request,
   which throws away unsaved work in code that briefly opens a request
   context (Flask-SQLAlchemy already cleans up).
9. Smaller broken imports in rarely used paths: `app/discord/notifications.py`
   (`Session`), `data_management_routes.py` (`Stat`).
10. `Throw.opposition_team` is never filled in when recording, so the
    opposition filter on the connections chart never matches anything.
11. 25 unused variables, 6 `raise` without `from`, and ~240 broad
    `except Exception` blocks; `process_player_stats` (app/stats/players.py)
    is still one 250-line function.

## Done

**Security**
- Hard-coded admin credentials removed from `run.py` and the old admin
  scripts (deleted); `flask create-admin` creates admins.
- Public `/debug-info` (would have shown the database password) deleted.
- `SECRET_KEY` has no built-in fallback.
- Third-party `myninja.ai` script removed from 29 templates.

**Teams**
- Only superadmins switch, add or edit other teams; team admins see only
  their own. Superadmins default to their own team.
- Lookups by id check the team: player feedback, quick capture, tournament
  bulk update (now coach-only), fitness metric edit/delete, player linking
  (players could previously link their account to anyone).
- Deleting a team works on Postgres and covers every table.

**Stats** (`app/stats/` for calculations, `app/routes/stats/` for pages)
- One player-stats calculation and one PER formula used by every page; the
  old per-player path undercounted catches and reported 0 break throws.
- Team CSV export works and fills every column; `games_played` is per player.
- Player conversion rates are real (the radar's O-line value was always 0).
- Dashboard ~1,660 -> ~90 queries; team page ~4,300 -> 20 (24-game season).
- The stats cache clears whenever stats data changes.
- No debug routes; data-changing maintenance is admin-only POST buttons on
  Data Management.

**Data**
- JSON ZIP backups include tables with dates (older backups don't).
- Postgres assigns ids again (migration resets sequences; the 29
  `max(id) + 1` workarounds are gone).
- `play` columns and `point.point_outcome` (undoing a goal used to fail)
  are handled by migrations, not boot-time scripts.

**Other bugs**
- Admin menu crash with Discord off; missing `AdminSessionRSVPForm` import.
- Error pages that rendered missing templates (playbook, theory, clip share
  links), the blank database-error message, and 404s returned as 500s.
- Pages whose templates were never written removed (drill viewer, fitness
  model, add theory video, the unregistered `drill_routes` module).

**Tidiness**
- ~190 lint fixes (unused/duplicate imports), 14 one-off scripts deleted,
  `__pycache__` untracked, badge colours in one macro file.
