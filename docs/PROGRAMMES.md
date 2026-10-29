# Training programmes

**Training > Programmes** lets any club build, publish and run its own
off-season (or any other) training programmes on the website: no code
changes and no developer needed. Thundering Herd's 2025/26 off-season plan
is one programme among many: it is a data file
(`imports/programmes/thundering-herd-2025-26/`) imported through the same
spreadsheet import any club can use.

Code: `app/models/programme.py`, `app/utils/programmes.py` (versions,
copies, scheduling, validation, dashboard), `app/utils/programme_import.py`
(spreadsheet import/export), `app/routes/programmes.py`,
`app/templates/programmes/`. Tests: `tests/test_programmes.py`.

Programmes replace the older Off-Season pages (`/off-season`), which have
been removed along with their tables.

## Who can do what

Clubs are the existing teams (`TeamOrganization`); roles are the existing
roles. Every request is checked on the server.

| Who | Can |
| --- | --- |
| Coaches, captains, team admins | Build, copy, import, publish and archive their club's programmes; add their club's players; see the dashboard; log sessions and record results for their players; export. |
| Players | See the published programmes they're on; log their own sessions and record their own test results. Nothing else. |
| Other clubs' coaches | See and copy a programme only when its club shares it as a template, and then only its **published content**. Never its players, logs, results or coach notes. |
| Superadmins | Whatever the team they've switched to allows. |

Every lookup is scoped to the current club; a programme, row, enrolment or
log from another club is a 404. Players can only ever reach their own
enrolment.

## Data model

```
Programme (club-owned; kind = programme | template; schedule; pauses; sharing; source)
 └─ ProgrammeVersion (draft -> published -> superseded)
     ├─ ProgrammeTrack (name, first week number, start offset)
     │   └─ ProgrammeWeek (position, title, kind: training | deload | rest, objective, skills)
     │       └─ ProgrammeSession (type, required | optional | alternative + group,
     │           │                warm-up, cool-down, cues, links, what players log)
     │           └─ ProgrammeExercise (name; sets, reps, distance, duration, rest,
     │                                  intensity, tempo, instructions: all optional)
     ├─ PerformanceTest (unit, measurement, attempts, aggregation, higher/lower is better, limits)
     └─ ProgrammeMilestone (baseline | retest | milestone, in a week, covering some/all tests)

ProgrammeEnrolment (player on a programme, on a version, from a start point)
 ├─ SessionLog (-> the exact session row logged; done | partial | skipped; minutes, RPE, ...)
 └─ TestResult (-> the exact test row; attempts and the aggregated value)
```

- Definitions (programme, versions and their content) are separate from
  enrolments, and prescribed sessions are separate from logs.
- Templates and club programmes are the same model with a `kind`; copying
  makes a new, independent programme with fresh rows.
- Every content row has a stable `key` (uuid). A new draft copies keys
  unchanged, so "the same session" is followed across versions by key,
  never by name or week number.
- Every table carries `team_organization_id`, so a club's data download and
  deleting a team (`app/utils/team_data.py`) cover programmes automatically.
- Nothing references another club's rows: a copy of a shared template
  records its source (name, club, version, author) as text.

## Versions: what publishing does

- Coaches only ever edit a **draft**. Published versions are frozen: their
  rows are never edited or deleted (the builder 404s on them).
- **Publishing** turns the draft into the live version and supersedes the
  previous one. By default players on the programme move to the new
  version; the coach can instead keep them on their current version and
  move them later (Players > Change).
- **Logs and results are never rewritten.** Each points at the exact row it
  was recorded against (in the old version) and keeps that row's key.
  On the new version a session still counts as done when its key is still
  there (e.g. it was renamed or its exercises changed). Logs for sessions
  that are no longer in the programme stay on the player's page under
  "From earlier versions".
- New players always join the live version.

## Scheduling

Nothing about week counts or week mappings is in the code.

- A programme has any number of tracks, each with its own length, its own
  week numbering (from 0 or 1) and a start offset in weeks.
- **Calendar** programmes count weeks from the programme's start date
  (everyone on the same week). **Relative** programmes count from each
  player's own start date.
- **Rest/deload weeks**: rest weeks have nothing to log and never count as
  missed.
- **Optional** sessions never count as missed; **alternative** sessions in
  the same group count once (do any one).
- **Late joiners** start at a programme week the coach chooses (defaults to
  the current week); earlier weeks aren't expected of them.
- **Pauses** (programme-wide in Settings, or per player) push every week
  from the pause's start back by its length: pausing and extending.
- **Templates** have no dates; copy one into a programme with a start date
  for a new season.

## Completion, missing data and the dashboard

The dashboard is built from the programme's own sessions and tests, so a
club without sprint tests or recovery tracking simply doesn't see them.

- A required session (or alternative group) is **due** once its week has
  ended. Due with no log = **not logged**; a player saying they skipped it =
  **skipped**. The two are counted separately and an unlogged session is
  never treated as skipped.
- Numbers that can't be worked out yet show as `—`, not 0 (no sessions due,
  no RPE logged, no second test result).
- Workload (session RPE x minutes) and recovery (soreness, sleep) appear
  when switched on in Settings and players are asked for those numbers.
- Test changes compare the baseline (or first) result with the latest,
  using the test's own direction (lower or higher is better).
- Players to follow up: two or more sessions not logged, completion under
  50%, nothing logged for two weeks while sessions are due, or a testing
  day passed with no result.

## Setting up a programme (a coach's view)

1. Training > Programmes > **New programme** (or **Import spreadsheet**, or
   copy a template).
2. **Build**: add tracks (length, first week number, offset); open a week to
   set its title/objective and add sessions; open a session to set its
   type, requirement, warm-up/cool-down/cues/links, what players log, and
   its exercises. Weeks and sessions can be reordered, duplicated and
   deleted.
3. **Tests**: add the tests this programme uses and the testing days.
4. **Preview** as a player, then **Publish** (it lists anything that blocks
   publishing first).
5. **Players**: add players, choosing where late joiners start.
6. **Dashboard** and **Export** (programme structure, tests, a progress
   report CSV).

To change a running programme: **Start a new draft**, edit, publish.

## Thundering Herd 2025/26

`imports/programmes/thundering-herd-2025-26/` holds the plan from the
"Thundering Herd Off-Season Training Plan 2025/2026" (v2.0) as import
files: four tracks (Sprint & Agility weeks 1-10, Conditioning weeks 0-15,
Throwing weeks 1-16 with a phase a month, Gym weeks 1-16 with the two gym
programmes as alternatives and optional core work), plus three sprint tests
with a baseline in sprint week 1 and a retest in week 10. Import it with:

```
flask import-programme imports/programmes/thundering-herd-2025-26 --team <slug> --name "Off-Season Training Plan 2025/26" --start 2025-10-20
```

then check and publish it under Training > Programmes. The plan document
doesn't name the three tests, so `tests.csv` uses 10 m sprint, 30 m sprint
and 5-10-5 pro-agility: edit them in the builder (or the CSV) to match.

## Not built (deliberately)

No public template library or marketplace (sharing is between clubs on
this site, opt-in per programme), no file uploads (links only), no billing.
