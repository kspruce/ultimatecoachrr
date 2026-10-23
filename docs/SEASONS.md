# Seasons and squads

A club runs one season per calendar year ("2026"). Each season keeps its own
games, tournaments, sessions and roster, so starting a new season never
deletes anything.

## What you see

Pages show the **current season** unless you pick another one from the
season menu (the calendar badge at the top right). Pick **All time** to see
everything. Your choice is remembered until you change it. While you're
looking at another season, a banner offers a link back to the current one.

Season scoping applies to the homepage numbers, the stats pages and CSV
export, the games, tournaments and sessions lists, and the team roster.
Player pages show a row per season plus career totals.

## Starting a new season

Team settings → **Seasons & squads** → **Start <year> season**:

1. Set the dates (1 January to 31 December by default).
2. Untick anyone who isn't carrying on. You can change each player's squad,
   shirt number and position for the new season.
3. Save. The new season becomes current. Players who were unticked are
   marked as having left last season's roster and are no longer active, so
   game-day pickers and sign-ups skip them. They keep their account and can
   still see their past seasons.

## Editing seasons

Every season, past ones included, stays editable: its dates, its roster
(squad, shirt, position, status: active, injured or left) and which season
is current. A season can be deleted only when it has no games, tournaments
or sessions.

New games, tournaments and sessions go into the season their date falls in.
If no season covers that year yet, one is created. Undated ones go into the
current season. A tournament's games follow its season and squad.

## Squads

Clubs with more than one team (e.g. 1s and 2s) can add squads. Squads share
the club's playbook, theory and drills, but each has its own roster for each
season, and games and tournaments can be assigned to a squad. The season
menu can then narrow pages to one squad. Deleting a squad keeps its players,
games and tournaments; they just no longer have a squad.

## For developers

- Models: `app/models/season.py` (`Season`, `Squad`, `SeasonRoster`);
  `season_id` on `game`, `tournament` and `session_plan`, `squad_id` on
  `game` and `tournament`. The `Tournament.season` text label is kept in
  step for older code.
- Logic: `app/utils/season.py`. Use `scope_games()`, `scope_tournaments()`,
  `scope_sessions()` and `season_players()` to follow the season switcher.
- `Player.active` always means "on the current season's roster and hasn't
  left", so existing `active=True` queries offer this season's roster.
- Existing teams are set up the first time they're opened: a season for each
  year they have data in, rows put in their season, rosters filled from who
  played. To do it for every team up front, run `flask backfill-seasons`
  (safe to run more than once).
