# Code health (updated October 2026)

Checked with ruff, bandit, radon, a read-through, and by running the app and
its migrations against a local Postgres. The test suite (`tests/`) runs on
SQLite and Postgres in GitHub Actions on every pull request.

## Still to do

**You need to do these yourself**
1. **Change the admin password.** The old one is still in git history (and
   so are the seed passwords that were in `db_manager.py`).
2. **Check `SECRET_KEY` is set in Railway's Variables.** `.env` is no longer
   committed, so the live site must get it from Railway.

**Code**
3. 25 unused variables, 6 `raise` without `from`, and ~240 broad
   `except Exception` blocks; `process_player_stats` (app/stats/players.py)
   is still one 250-line function. Several log calls pass the error as a
   second argument with no `%s` (`logger.error("...:", str(e))`), so the
   message is lost.

## Done

**Code (October 2026, second pass)**
- `error_handlers.py` no longer calls `db.session.remove()` after every
  request (Flask-SQLAlchemy does it when the app context ends); a failed
  request still rolls back.
- The unused `Stat` import in `data_management_routes.py` is gone.
- Throws get their game's opponent when saved (and old ones were filled in
  by migration `b2d4f6a8c0e3`), so filtering connections by opponent works.
- The separate `/cutting-skills` blueprint (no stat-taker check) is gone;
  the stat recorder uses `stat.record_cutting_skill`.
- The off-season section (routes, models, templates, tables) is removed;
  Programmes replaces it.

**Security**
- Hard-coded admin credentials removed from `run.py` and the old admin
  scripts (deleted); `flask create-admin` creates admins.
- Public `/debug-info` (would have shown the database password) deleted.
- `SECRET_KEY` has no built-in fallback.
- Third-party `myninja.ai` script removed from 29 templates.

**Teams**
- Cross-team audit (October 2026): every page, search box, filter, JSON
  endpoint, form submit and delete was probed as another team's captain and
  player with Thundering Herd's ids. Fixed: scouting/session filter dropdowns,
  session component plays, fitness metric lists and lookups, clip segment
  delete, stat recording, game/tournament player selection, session quick
  check-in and off-season track weeks. `team_player_ids()` drops posted
  players from other teams; `tests/test_team_isolation.py` covers each one.
- The drill library search, skill level and focus area filters work.
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

**Redundant and unfinished pages**
- One data management page: `/admin/data-management` redirects to the
  enhanced page, whose export/import buttons used to be answered by the old
  page's routes. Both exports include the link tables.
- One session RSVP page (the calendar's copy of `/sessions/<id>/rsvp` hid
  the fuller one); a test fails if two routes ever share a URL again.
- The drill editor (`/sessions/drills/editor`) works: players, discs,
  cones, cuts, throws and text on a field, saved as a diagram (PNG, SVG and
  the editable drawing). Linked from the drill library and each drill.
- Session PDF download uses Playwright, like the playbook export.
- Fitness goals: `FitnessGoal` model, a goals page per player, goals
  complete themselves when a record meets them.
- Removed `/team/debug`, the unused drill search/duplicate APIs,
  `drill_viewer.js`, seven unused templates and `index.html.orig`; the clip
  library planning notes moved from `app/update/` to `docs/clip-library/`.

**Tidiness**
- ~190 lint fixes (unused/duplicate imports), 14 one-off scripts deleted,
  `__pycache__` untracked, badge colours in one macro file.
