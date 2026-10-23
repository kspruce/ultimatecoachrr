# Training: schedules, availability and session plans

This replaces the availability spreadsheet. Coaches set up when the team
trains, players say which dates they can make, and coaches plan each
session knowing who's coming.

## For coaches

1. **Training schedule** (Training → Training Schedule). Add one row per
   regular session: day, time, place, first and last date, and who it's for.
   For example:
   - *Saturday training*: Saturdays, all season, everyone (no squad ticked).
   - *2s midweek*: Tuesdays, Nov to Jan, 2s only.
   - *1s midweek*: Wednesdays, Nov to Jan, 1s only.

   Every date is made straight away (open-ended schedules roll forward
   nightly), so players can answer weeks ahead. You can add "weeks off" to
   cancel dates up front, and any training that clashes with a tournament is
   flagged. Changing a schedule moves every future date that hasn't been
   planned yet.
2. **Who's coming** (Training → Who's Coming). This is the grid: players
   down the side, dates across the top. Click a cell to change it
   (blank → Yes → Maybe → No). The bell under each date reminds everyone on
   Maybe or with no answer. From here you can export a CSV, or import your
   old spreadsheet (player names in the first column, one date per column).
3. **Plan a session**: open a date and choose *Plan this session*. Add
   blocks, or pick drills from the library, then drag them into order. Clock
   times and the total are worked out for you. *Copy* last week, start from a
   template, or *Save as template*. Plans stay a draft until you click
   *Publish to players*.
4. **Register**: *Take the register* starts with everyone who said Yes
   marked present, so you only change the people who didn't come.
5. **Cancel** a date from its page. Players who said Yes or Maybe are told by
   Discord message or email.

Team settings → **Sessions** controls what players see about who else is
coming (names, just the numbers, or nothing), when they see published
plans, and reminders (on by default, 7 days before).

## For players

Training → **My Availability** lists every upcoming session for your
squad, with Yes / Maybe / No buttons that save as you tap. Set a **usual
answer** for each schedule ("usually at Saturdays") and you only need to
change the exceptions. If you're on Maybe (or haven't answered) a week
before a session, you get one reminder.

## Discord

Team settings → **Discord**:

- **Add to Discord** adds the site's bot to your server; then pick the
  channel it posts in. Each week (on the day you choose) it posts the
  coming week's sessions, each with Yes / Maybe / No buttons. Players who
  tap them get their answer saved, the same as on the site.
- Players **Connect Discord** from their profile (they sign in with
  Discord, so nobody needs to type in an ID). Connected players get their
  reminders as a Discord message instead of an email.
- No bot? Paste a channel **webhook** URL instead. Posts then go out
  without buttons, each with a link to answer on the site.

### Setting up the bot (once per site)

A superadmin follows the steps at `/discord/setup`: create an application
in the Discord developer portal, set `DISCORD_CLIENT_ID`,
`DISCORD_CLIENT_SECRET`, `DISCORD_BOT_TOKEN` and `DISCORD_PUBLIC_KEY`, add
the redirect URL shown on that page, and click *Set it for me* to point
button clicks at the site. Nothing runs in the background for Discord:
button clicks arrive as signed HTTP requests to `/discord/interactions`.

## For developers

- Models: `app/models/schedule.py` (`TrainingSchedule`,
  `ScheduleAvailability`, `SessionTemplate`, `SessionReminder`). On
  `SessionPlan`: `schedule_id`, `squads`, `status` (scheduled / cancelled),
  `is_published`.
- Answers are always saved through `app.utils.rsvp.set_rsvp`, as
  `attending` / `maybe` / `not_attending`. `answers()` also fills in usual
  answers, marked `usual`. `expected_players()` decides who a session is for
  (its squads, or everyone, plus anyone who has answered).
- Making dates: `app/utils/schedules.py`. Reminders and cancellation notices:
  `app/utils/reminders.py`. Pages: `app/routes/training.py`.
- Background jobs are in `app/scheduler.py`. They start on the first web
  request: nightly, schedules make their next dates; hourly, reminders and
  weekly Discord posts go out. Everything they do is safe to repeat. Run the
  same jobs with `flask training-jobs` (for example from cron, with
  `SCHEDULER_ENABLED=0`).
- Discord: `app/discord/` (`api.py` talks to Discord over HTTP, `messages.py`
  builds posts, `interactions.py` handles button clicks, `notify.py` posts to
  a team, `events.py` announces new tournaments, games, clips and theory).
- The season plan's *Build sessions* fills in a schedule's date that week
  for the same squads, instead of making a new session.
