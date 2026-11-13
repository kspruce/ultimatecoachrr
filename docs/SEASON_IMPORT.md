# Importing a season plan

`flask import-season` loads a season of session plans, drills, standard cards
and drill diagrams from one JSON file (`"schema": "herd-session-v1"`).
A small working example is in `tests/fixtures/sample_season.json`.

```
flask import-season season.json --images-dir images/ --team-org <id> --dry-run
flask import-season season.json --images-dir images/ --team-org <id>
```

- Everything is matched on `external_id` within the team, so re-running the
  same file updates rows in place and reports them as unchanged.
- The whole file is checked first; if anything is wrong, every problem is
  listed and nothing is written.
- `--dry-run` runs the full import in a transaction and rolls it back.
- Nothing that isn't in the file is deleted. A session's components are
  rebuilt only if they changed (attendance and RSVPs are kept; playbook links
  to that session's components are dropped).
- Diagram images are stored in the database (Railway's disk is wiped on
  every deploy) and served from `/sessions/drills/diagrams/...`. PNG, JPEG,
  GIF and WebP up to 5MB; SVG optional alongside.

## Drill library files

`imports/drills/` holds drill-only files in this format. Import them before
building (or rebuilding) the season plan's sessions, so the sessions link to
the drills:

- `grut-drills.json`: the 9 GRUT drills the season plan uses (four more GRUT
  videos are theory cards 41-44).
- `herd-drills.json`: about 90 drills and games the 2027/28 sessions use (the
  Ian French games, the club staples such as the 4v3 mini and 4v4 continuous,
  and the split-session drills), each with what it's for, how it runs,
  coaching points, set-up, numbers and the weeks it's used. The split-session
  tables have no "How it runs" column, so this is where most of their
  activities get their details. Drills the plan only summarises say to check
  the full version in their source.

```
flask import-season imports/drills/grut-drills.json --team-org <id>
flask import-season imports/drills/herd-drills.json --team-org <id>
```

Then rebuild the sessions (**Season plan > Sessions > Build sessions**) so
existing sessions pick up the links.

Diagrams drawn in the drill editor are kept when the file is re-imported.

## Format

| JSON | Stored as |
|---|---|
| `season` (top level) | `SessionPlan.season` |
| **drills[]** `external_id`, `title`, `description`, `setup_instructions`, `source`, `focus_area`, `equipment_needed` | same-named `SavedDrill` columns |
| drills[] optional: `recommended_duration`, `min_players`, `max_players`, `skill_level` | same-named columns |
| drills[] optional: `video_url` (YouTube, Vimeo or Google Drive link) | the drill's video, shown on the drill page even after a diagram is drawn. Leave the key out to keep a video added on the site; `null` removes it |
| drills[] `diagrams[]`: `file`, `svg`, `step_label`, `caption`, `source` | `DrillDiagram` rows, in list order; paths are relative to `--images-dir` |
| **cards[]** `external_id`, `card_code`, `title`, `summary`, `sections[{heading, lines}]` | `SavedDrill` with `is_standard_card`; summary + sections become a Markdown description. Cards may have `diagrams` too |
| **sessions[]** `external_id`, `title`, `week`, `week_commencing` (YYYY-MM-DD), `phase_number`, `phase`, `block`, `squad` (`joint`/`1s`/`2s`), `run_by`, `kit`, `aim`, `sources` | `SessionPlan` (`week` → `week_number`, `phase` → `phase_name`) |
| sessions[] `points` (or `learning_points`) | list of strings |
| sessions[] `words` (or `key_terms`) | list of `[term, meaning]` pairs |
| sessions[] `notes` | a list becomes Markdown bullets; a string is kept as is |
| sessions[] optional: `date`, `start_time` (HH:MM), `end_time`, `location`, `focus_area`, `session_type` | same-named columns. With `start_time` + `length_minutes` and no `end_time`, the end time is calculated. Without `date` the date is left empty |
| sessions[] `activities[]`: `name`, `type`, `mins`, `drill_id`, `how`, `coach`, optional `notes`, `focus_area` | `SessionComponent` in list order (`how` → description, `coach` → coach_cue). `type` is one of warmup, drill, scrimmage, cooldown, discussion, water, other. `drill_id` is a drill or card `external_id`, from this file or an earlier import |
| `time` | ignored (order and `mins` define the timeline) |

# Building sessions from the season plan

The season plan (`flask import-season-plan`) is the one place to write
sessions. Coaches open **Season plan > Sessions**, set the training day, times
and location for joint and split sessions, check the preview and press
**Build sessions**. Re-running the build updates sessions in place, and once
sessions have been built:

- saving a week on the site (**Edit week**) rebuilds that week's sessions;
- re-importing the plan rebuilds every week's sessions in the same
  transaction (`--build-sessions` builds them on an import before the first
  build; `--dry-run` reports what would change).

## What the week's notes need

Inside each `## Week N · date · title` section:

| In the notes | Becomes |
|---|---|
| A table starting `Time \| Activity \| How it runs \| Source` | The week's **joint** session; each row is an activity (`Activity` → name, `How it runs` → description, `Source` → note) |
| A table starting `Time \| 1s ... \| 2s ... \| Source` | A **1s** and a **2s** session; a 2s cell of `Same` copies the 1s cell |
| The bold line above a table (`**Light joint session (about 2 hours)**`) | Its label; a length in it sets how long the last activity runs, otherwise it runs to the session's end time |
| `**Learning points:** (1) ... (2) ... (3) ...` | The learning points of every session that week |
| Everything else (what to tell players, coaching notes, ...) | The session notes |

Activity lengths come from the gap between one row's `Time` and the next.
Long cells are split at the first `:`, `;` or `. ` into a name and a
description, and so are short ones written as "Name: how it runs" (a detail
of 25 characters or more after the colon). In the split table, a 2s cell of
`Same`, `The same` or `Same drill at stall 7` copies the 1s activity, with any
change ("2s: at stall 7") added to its description. Activity types are
guessed from the name (warm-up, water, scrimmage/free game/7v7,
recap/welcome/briefing → discussion, otherwise drill). Weeks with no such
table (breaks, tournaments) get no sessions.

An activity (other than a warm-up or water break) is linked to a drill in the
team's library when their names match, ignoring case, punctuation, bracketed
parts such as "(GRUT)" and "a"/"the". The match also tries each side of a
"Round 1: Golden Arm" name, the name without qualifiers such as ", stall 5" or
"then ...", and a library name that starts the activity name ("Extended mark
refresher" → Extended mark; the longest wins) or that the activity name starts
when only one does ("4v4, stall 7" → 4v4 continuous). One-word library names
and theory cards only match exactly. The session page, print view, PDF and run
mode show the linked drill's description when the activity has none of its
own.

## What the plan owns

Built sessions have `external_id` `plan-<season>-w<NN>-<joint|1s|2s>`. The
plan owns their title, date, times, location, aim (the week's theme for that
squad), learning points, notes and activities, so edits made on the session
pages are replaced on the next build (the session pages say so). Attendance,
RSVPs and the session type are never touched. A session the plan no longer
has is deleted, unless anyone has RSVPed or been marked for it, in which case
it is kept and the build warns. The week page lists the week's sessions, and
the week's "Linked session plan" points at its joint session unless a coach
linked it to a session of their own.
