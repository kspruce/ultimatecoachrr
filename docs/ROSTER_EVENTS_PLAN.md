# Roster, Tournaments, RSVPs & Calendar — Improvement Plan

Status: **implemented** (all five phases). Defaults chosen for the open
questions: only coaches see who said what (players see totals); selection has
picked / reserve / not picked; `line_preference` is kept; emails go to
players with an account (they can turn them off on their account page) and a
short note goes to Discord when a webhook is set up; players see the
selection only once the coach publishes it.

Where it lives:
- `app/utils/rsvp.py`: answers, eligibility, picks, game line-ups
- `app/utils/event_notify.py`: emails/Discord, daily reminders
  (in-process at 09:05, or `flask send-rsvp-reminders`; `RSVP_REMINDERS=0`
  turns the in-process job off)
- `app/utils/schedule_parse.py`: pasted schedules
- `app/routes/tournament.py` + `templates/tournament/detail.html`: the hub
- `app/routes/calendar_routes.py`: `/calendar/events` feed and
  `/calendar/feed/<token>.ics`
- `app/routes/team.py`: inline roster editing and quick add
- Migration `a3c5e7f9b1d2`; tests in `tests/test_tournament_hub.py`

Goal: a coach should be able to go from "we're going to Nationals" to "everyone
knows if they're picked and which games they play" in a few minutes, and a
player should be able to answer "am I going, and when do I play?" in one tap.

---

## 1. How it works today

### Roster
- `Player` is the person; `SeasonRoster` (app/models/season.py) holds the
  per-season shirt, position, squad and status (`active` / `injured` / `left`).
- Two separate places edit the roster:
  - **Team → Roster** (`team.index`, app/routes/team.py:29) — filter list,
    add/edit/delete one player at a time, CSV bulk import.
  - **Seasons → Roster** (`seasons.roster`, app/routes/seasons.py:223) — table
    for squad/shirt/position/status of one season.
- `Player.active` is a denormalised copy of "on the current season roster",
  kept in step by `sync_active_flags`.

### Tournaments and games
- Tournament form: name, dates, location, season, squad (app/routes/tournament.py).
- Games are added from the tournament page one at a time (`game.add`) or with
  "Add Multiple Games" (`game.add_multiple`).
- `game.add` auto-assigns players: those with an `attending` RSVP for the
  tournament, else the whole active roster.
- `game.add_multiple` assigns **nobody**.

### Selection and RSVPs (three overlapping concepts)
1. **RSVP** — player says attending / maybe / not attending (+ notes).
   Three entry points: tournament page form, calendar modal (`/api/rsvp`),
   and a JSON branch in `tournament.rsvp`.
2. **Selection** — coach ticks `selected_by_admin` on the RSVPs page
   (`tournament.rsvps` → `update_selections`).
3. **Game assignment** — `GamePlayer` rows, set on the "Assign Players to
   Games" page (only selected players are listed) or on the game page.

### Calendar
- FullCalendar month/week/list view (app/routes/calendar_routes.py,
  app/templates/calendar/index.html) showing **upcoming** sessions and
  tournaments only. Click → modal with RSVP buttons and coach links.

---

## 2. Problems found

### Bugs (fix first)
| # | Where | Problem |
|---|-------|---------|
| B1 | `team.index` (routes/team.py:68), `edit_player` (:200), templates | `Player.line_preference` was dropped from the model (migration 7729e5ca9089) but the roster filter still queries it → filtering by line crashes; edits to it are silently lost. |
| B2 | `tournament/detail.html` | The RSVP/selection card is gated on `is_admin`, but the routes are `coach_required` → plain coaches never see "Manage RSVPs" or "Assign Players". |
| B3 | `calendar_routes.index` | Only `start_date >= today` — a tournament already in progress disappears, and clicking "prev" shows empty months. |
| B4 | `calendar_routes.api_rsvp` | `status` isn't validated (any string is stored). |
| B5 | `game.add_multiple` | `int('')` on a blank score → 500; no players auto-assigned; season/squad not applied. |
| B6 | `update_selections` | Ticking a player with no RSVP creates an RSVP with `status='attending'` and note "Added by admin" — fakes the player's answer. Ticking a player who said "not attending" gives no warning. |
| B7 | `game.add` auto-assign | Comment says "attending or admin-selected" but only `attending` is used; fallback uses `Player.active`, ignoring the tournament's squad. |
| B8 | `tournament.rsvps` "No RSVP" list | Uses `Player.active` (whole club) rather than the tournament's season/squad roster, so 2s players show as "no reply" for a 1s tournament. |

### Usability
- Coaches juggle **four pages** for one tournament (detail, RSVPs, selection,
  assign) with three different save buttons; easy to lose unsaved ticks.
- Two roster editors with overlapping fields; no single "who's on the team".
- Games must be entered one at a time or via a clunky multi-row form; no way
  to paste a schedule.
- No RSVP deadline, no reminders, no way to chase non-responders.
- Players aren't told when they're selected / not selected or which games
  they're in.
- Player's tournament page says "selected by the admin" — wording and
  emphasis are wrong; the important information (picked? which games? when?)
  is buried.
- Games aren't on the calendar; game times don't exist (date only).
- No calendar subscription (Google/Apple), no filter by squad or type.
- Mobile: RSVP pages are wide Bootstrap cards/tables; the calendar month grid
  is hard to tap on phones.

---

## 3. Target design

### Principle: one tournament page, three tabs
Replace detail / RSVPs / assign with a single **Tournament hub**
(`/tournaments/<id>`), tabbed:

1. **Overview** — dates, location, squad, deadline, record, games list.
   For players: big status card ("You're picked ✔ / Waiting on coach / Not
   picked") with one-tap RSVP buttons.
2. **Squad** (coach) — one table of every eligible player:
   `Name | Their answer | Note | Picked ☐`. Columns sortable, filter chips
   (Attending / Maybe / No reply / Can't). Counts at top
   (e.g. *14 picked · 3 gender-match F · 5 handlers*). Autosave each tick
   (no "Save" button to forget). Warning badge if picking someone who said no.
   "Nudge non-responders" button.
3. **Games** (coach edits, players read) — schedule list with time, field,
   opponent; assignment grid `players × games` with checkboxes, "all picked
   players" shortcut per game, row/column totals. Players see only their own
   row: "You're playing: 9:00 vs X (Field 3), 11:00 vs Y…".

Keep the old URLs as redirects to the right tab.

### Data model changes
- `Tournament`: `rsvp_deadline` (date), `notes` (text, shown to players),
  `squad_size_target` (int, optional), `published_selection` (bool — players
  only see "picked/not picked" once the coach publishes).
- `TournamentRSVP`: rename concept in UI to **availability**; split coach
  pick into its own nullable `selection` state (`picked` / `reserve` /
  `not_picked` / NULL) instead of overloading `selected_by_admin`, and allow a
  coach-pick row without inventing a player `status` (make `status` nullable
  = "no reply").
- `Game`: `start_time` (time), `field` (string).
- Migration backfills `selection='picked'` where `selected_by_admin` is true.

### Roster
- One **Roster** page (merge Team → Roster with Seasons → Roster):
  - Season + squad pickers at top (already exist in context bar).
  - Inline-editable table (shirt, position, squad, status) with autosave,
    same pattern as the Squad tab.
  - Row click → player profile. Add player = small inline row / modal,
    "Invite" button that copies an invite link.
  - Keep CSV import, add "paste names" quick add.
  - Show account status per player (linked / invited / no account) so coaches
    see who can't RSVP yet.
- Resolve B1: either restore `line_preference` as a column (it's used in UI
  and CSV import) or remove it everywhere. Recommendation: restore it — it's
  useful for selection and line-building.

### Adding tournaments and games
- Tournament form: add deadline, notes, squad size target; default dates
  from last tournament; "Copy from previous tournament" (same location/squad).
- After creating a tournament, land on its hub with a prompt:
  "Add the schedule" and "Ask players for availability".
- **Quick schedule entry**: one textarea, one line per game
  (`Sat 09:00 vs Rival FC Field 3`), parsed into a preview table the coach
  confirms. Keep the row-by-row form as fallback; fix B5.
- New games in a tournament auto-assign the **picked** players (not
  RSVP-attending, not whole club). Standalone games default to the squad's
  current roster.

### RSVPs (players)
- Single shared RSVP service (`app/utils/rsvp.py`) used by the form, the
  calendar API and any future one-tap links — validates status, applies
  deadline, writes the row. Removes the duplicated code in
  `tournament.rsvp` / `calendar.api_rsvp`.
- One-tap buttons everywhere a player sees an event (home dashboard,
  calendar modal, tournament page) — no separate RSVP page needed; note box
  is optional and collapsible.
- After the deadline: player can still change, but it's flagged "late" to
  the coach.
- "My events" list on the home page: upcoming sessions/tournaments with
  answer status and "needs reply" badge.

### Notifications
- Reuse existing Discord webhooks + email (app/discord, app/utils/email.py):
  - New tournament → "Reply by <deadline>" with link.
  - Reminder N days before deadline to those with no reply (scheduled job
    like `notify_upcoming_tournament`) and a manual "Nudge" button.
  - Selection published → each player told picked / reserve / not picked.
  - Game schedule published/changed → picked players get their games.
- Per-player opt-out stays in their profile.

### Calendar
- Load events by visible range via a JSON feed
  (`/calendar/events?start=&end=`) instead of embedding only future events —
  fixes B3, makes history browsable.
- Add **games** (with times when set) and show tournaments as multi-day bars.
- Colour + legend by type; badge per event for the viewer's answer
  (✔ / ? / ✖ / needs reply) and "picked".
- Filters: type (sessions/tournaments/games), squad, "only mine".
- Default to **list view on phones**, month view on desktop.
- Coaches: click an empty day → "Add session / tournament / game" prefilled
  with that date. Event modal shows counts (12 yes · 3 maybe · 6 no reply)
  with a link to the hub.
- **Subscribe**: per-user secret iCal feed (`/calendar/<token>.ics`) so
  players get events in Google/Apple calendar, including only games they're
  assigned to.

---

## 4. Phased delivery

Each phase is shippable on its own and keeps existing URLs working.

**Phase 1 — Fix what's broken (small, low risk)**
- B1–B8 above, with tests in `tests/` for each.
- Shared RSVP helper (`app/utils/rsvp.py`) and status validation.

**Phase 2 — Tournament hub**
- Model fields: deadline, notes, selection state, game time/field + migration.
- Tabbed hub page; Squad tab with autosave picks and counts; Games tab grid.
- Player status card + one-tap RSVP on the hub.
- Old `rsvps` / `assign_players` routes redirect to tabs.

**Phase 3 — Schedule entry & roster merge**
- Quick-paste schedule parser with preview.
- Unified Roster page with inline editing, account status, invite links.

**Phase 4 — Calendar**
- Range-based JSON feed, games on calendar, filters, mobile list default,
  click-to-add for coaches, RSVP counts in modal.
- iCal subscription feed.

**Phase 5 — Notifications & reminders**
- Deadline reminders, nudge button, selection published, schedule changes,
  via Discord + email.

---

## 5. Testing & rollout
- Unit tests for the RSVP helper, selection logic, schedule parser, iCal
  output, and the calendar range feed (team scoping on every query).
- Route tests per role: player, stat_taker, coach, captain/admin — confirm
  coaches (not only admins) get the management UI (B2).
- Mobile check of hub, roster and calendar at 375px width.
- Migrations are additive; `selected_by_admin` kept until Phase 2 is
  verified, then dropped in a follow-up migration.

## 6. Open questions for the coach
1. Should players see each other's availability, or only the coach?
2. Do you want a "reserve" tier in selection, or just picked / not picked?
3. Keep `line_preference` (O/D/both) on players? (Plan assumes yes.)
4. Notifications: Discord, email, or both by default?
5. Should selection be hidden from players until the coach publishes it?
