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

## Format

| JSON | Stored as |
|---|---|
| `season` (top level) | `SessionPlan.season` |
| **drills[]** `external_id`, `title`, `description`, `setup_instructions`, `source`, `focus_area`, `equipment_needed` | same-named `SavedDrill` columns |
| drills[] optional: `recommended_duration`, `min_players`, `max_players`, `skill_level` | same-named columns |
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
description. Activity types are guessed from the name (warm-up, water,
scrimmage/free game/7v7, recap/welcome/briefing → discussion, otherwise drill),
and an activity whose name matches a drill in the team's library is linked to
it. Weeks with no such table (breaks, tournaments) get no sessions.

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
