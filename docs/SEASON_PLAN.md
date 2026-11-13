# Season plan

**Season plan** (switched on under Team settings > Features) plans a club's
season week by week: phases, a theme for every week (one for the whole club,
or a joint theme plus one per squad), milestones, long-form pages, session
notes that can be built into sessions, and classroom sessions.

Code: `app/models/season_plan.py`; routes in `app/routes/season_plan.py`
(viewing, weeks, sessions, classroom), `app/routes/season_plan_edit.py`
(creating and editing, spreadsheet import/export) and
`app/routes/season_plan_year.py` (the year view); helpers in
`app/utils/season_plan_build.py`, `season_plan_templates.py`,
`season_plan_sheet.py`, `season_plan_import.py` (markdown import and the
shared writer) and `season_sessions.py`. Tests: `tests/test_season_plan*.py`,
`tests/test_season_sessions.py`, `tests/test_classroom.py`.

## Getting a plan

A coach with no plan sees three ways in:

1. **Create a plan** (`/season-plan/new`): title, season, the first week,
   and phases with a name and a number of weeks each. The plan gets as many
   weeks as the phases add up to, each starting on a Monday. Optionally:
   squads with their own themes (ticked from the club's squads or typed),
   training days and times (used when building sessions), and whether players
   can see the overview, weeks and phases (on by default).
2. **Start from a template**: the same form, with the phases, a theme for
   every week, milestones and two pages filled in
   (`app/utils/season_plan_templates.py`: a 16-week season for one squad, and
   a 40-week year for two squads). Squad themes in a template are given by
   position and go to the plan's squads in the order listed.
3. **Import a spreadsheet** (`/season-plan/import`): see below.

A site admin can still import a markdown export (`flask import-season-plan`,
described at the top of `app/utils/season_plan_import.py`).

A new plan becomes the one everyone sees; older plans are listed under Edit
plan > Settings, where a coach can switch back to one or delete it (by typing
its season).

## Editing (Edit plan)

- **Settings**: title, season, summary; the first week (moves every week by
  the same amount); the number of weeks (adds weeks at the end, or removes
  empty ones from the end; a week with anything written in it stops the
  trim); squads (rename keeps their themes, remove deletes them).
- **Phases**: name, first and last week, aim, training focus, events,
  strategic anchor, colour, and a training programme (below). Phases can't
  overlap and are numbered in the order they start; weeks outside every phase
  are listed.
- **Milestones**: what, a week or a range of weeks, and optional wording for
  when ("After every event"). Sorted by week.
- **Pages**: markdown pages, each visible to players or not, in any order.
- **Player access**: what players can see. The overview tells coaches when
  players can see nothing.
- **Import / export**.

Each week's themes, notes and session notes are edited from the week
(Weeks > a week > Edit week): one field for the joint (or only) theme and one
per squad.

## Squads and themes

`SeasonPlan.squad_names` lists the squads with their own theme;
`SeasonWeek.squad_themes` maps each to its theme. With no squads a week has
one theme, labelled "Theme". The Weeks filter offers the plan's squads.

When sessions are built from session notes, a split table's columns are
matched to the plan's squads by name ("1s group", "Women (suggested)"); a
plan without squads matches the club's squads instead. Each squad's session
gets that squad ticked; its `SessionPlan.squad` label is set only for the
sessions page's joint / 1s / 2s filter values. Session ids are
`plan-<season>-w<NN>-<squad slug>`.

## Spreadsheet import and export

Download the Excel template from the import page (an Instructions sheet,
then `weeks`, `phases` and `milestones`), or a CSV of the weeks alone.

| Sheet | Columns |
| --- | --- |
| weeks | `week` (required), `week_commencing`, `phase` (number or name), `block`, `event`, `break` (yes), `theme`, a column per squad named after the squad, `classroom`, `off_pitch`, `session_title`, `session_notes` |
| phases | `phase`, `name`, `start_week`, `end_week`, `aim`, `training_focus`, `events`, `strategic_anchor`, `colour` |
| milestones | `when`, `what` (required), `start_week`, `end_week` |

- Weeks without a `week_commencing` count on from the start date given on
  the upload form (or from the first week that has a date).
- Without a phases sheet, the weeks' `phase` column makes the phases.
- The upload is checked and previewed first; problems are listed with their
  spreadsheet row. Rows can be corrected on the page and checked again.
- Importing for a season that already has a plan updates it (the same
  writer as the markdown import): weeks and phases match on their numbers,
  weeks and phases not in the sheet are removed, and coaches' notes, linked
  sessions, a phase's programme, pages and classroom sessions are kept.
- **Export this plan** writes the same workbook, so export, edit and import
  is a quick way to change many weeks.

## The year, and programmes in the plan

**The year** (coaches) shows the plan's phases and the club's dated training
programmes on one timeline, with self-paced programmes listed beside it.
Linking a programme to a phase (Edit plan > Phases) shows that week's
programme sessions on every week of the phase, for anyone who can see the
week. Only the programme's published version is shown, and only calendar
programmes (weeks counted from the programme's start date) can be placed.

Programmes have starter templates of their own (Training > Programmes >
Starter templates, `app/utils/programme_starters.py`): adding one makes a
draft programme from the chosen start date.

## Database

Migration `c7e9a2d4f6b8` replaced `season_week.firsts_theme` and
`seconds_theme` with `squad_themes`, added `season_plan.squad_names` (plans
that used the old columns get `["1s", "2s"]`) and `season_phase.programme_id`.
