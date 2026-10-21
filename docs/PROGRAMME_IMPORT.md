# Importing a training programme from a spreadsheet

Coaches import under **Training > Programmes > Import spreadsheet**. A site
admin can do the same from the command line:

```
flask import-programme imports/programmes/<folder> --team <team-slug> --name "Off-season 2026" --start 2026-10-05
```

Either way the programme arrives as a **draft**: check it in the builder,
then publish it. Nothing is written until the file has no errors, and the
same content is never imported twice into one club (the import is matched
on a hash of its rows; another club importing the same file gets its own
copy).

Download blank templates from the import page, or export any programme
(**Export programme / Export tests**): the export is the same format, so an
exported programme imports back unchanged.

## Files

| What | Spreadsheet (.xlsx) | CSV |
| --- | --- | --- |
| The programme | a sheet called `programme` (or the first sheet) | one file, UTF-8 |
| Tests (optional) | a sheet called `tests` | a second file |

The first row holds the column names (case and spaces don't matter:
`Week Title` = `week_title`). Unknown columns are ignored and listed as
warnings. Row numbers in error messages are spreadsheet rows, with the
header as row 1.

## The programme sheet

One row per **exercise**. A session with no exercises is one row; a rest
week with no sessions is one row.

Blank `track`, `week` and `session` cells carry on from the row above, so a
session's exercises can be listed under it without repeating everything.
Week and session details (title, objective, type...) can go on any of their
rows; the first one given wins and a different value later is reported.

| Column | Required | Meaning |
| --- | --- | --- |
| `track` | yes | Track name, e.g. `Speed`, `Conditioning`. Tracks run side by side. |
| `track_first_week` | | The number of the track's first week: `1` (default: the lowest week in the sheet) or `0` for Week 0, 1, 2... |
| `track_start_offset` | | Weeks after the programme start that the track begins (default 0). |
| `week` | yes | Week number within the track. Every week from the first to the last must have at least one row. |
| `week_title` | | e.g. `Acceleration fundamentals` |
| `week_type` | | `training` (default), `deload` or `rest`. Rest weeks have nothing to log and never count as missed. |
| `week_objective` | | What the week is for. |
| `week_skills` | | Supporting skills / key cues. |
| `session` | yes* | Session title. *Not needed on a rest-week row. Rows with the same title in the same week are one session. |
| `session_type` | | `sprint`, `agility`, `conditioning`, `strength`, `throwing`, `footwork`, `mobility`, `recovery`, `custom`, or any other word (kept as a custom type, e.g. `Plyometrics`). |
| `requirement` | | `required` (default), `optional` or `alternative`. |
| `alternative_group` | for alternatives | Alternatives in the same week with the same group: doing any one of them counts. |
| `session_minutes` | | Whole minutes. |
| `session_focus` | | Focus and instructions. |
| `warmup`, `cooldown`, `coaching_cues` | | Text. |
| `session_video` | | An `http(s)://` link. |
| `log_fields` | | What players record, comma separated: `duration_minutes`, `rpe`, `distance_m`, `soreness`, `sleep_hours`. Notes and done/partly/skipped are always offered. |
| `exercise` | | Exercise or drill name. Everything below needs it. |
| `block` | | e.g. `A1`, `Warm-up`. |
| `sets`, `reps` | | Text, so `3`, `6-8 per leg` and `AMRAP` all work. |
| `distance_m` | | Metres (a number). |
| `duration_s` | | Seconds (a whole number). |
| `rest`, `intensity`, `tempo` | | Text, e.g. `2 min`, `RPE 7`, `3-1-X`. |
| `instructions` | | Instructions and cues. |
| `exercise_video` | | An `http(s)://` link. |

Only the name is needed for an exercise: a throwing drill can have a
duration and instructions and nothing else.

## The tests sheet

One row per performance test.

| Column | Required | Meaning |
| --- | --- | --- |
| `test` | yes | Name, unique in the programme. |
| `unit` | yes | e.g. `s`, `m`, `reps`, `level`. |
| `measurement` | | `time`, `distance`, `count`, `score` or `other` (default). |
| `attempts` | | How many attempts a player records (default 1). |
| `aggregation` | | `best` (default), `mean` or `last` attempt. |
| `better` | yes | `lower` (e.g. sprint times) or `higher` (e.g. distances). |
| `min`, `max` | | Values outside these are refused when results are entered. |
| `description`, `instructions` | | How to run it, conditions. |
| `milestone_track` | with weeks | The track whose week numbers the next two columns use. |
| `baseline_week` | | Week of the baseline test. |
| `retest_weeks` | | Weeks of retests, comma separated, e.g. `6, 12`. |

Tests sharing a track and week are put on the same testing day.

## Example

```
track,track_first_week,week,week_title,week_type,session,session_type,requirement,alternative_group,exercise,sets,distance_m,duration_s,rest
Speed,1,1,Acceleration,,Sprint day,sprint,required,,10 m sprints,15,10,,Walk back
,,,,,,,,,20 m sprints,10,20,,Walk back
,,2,Rest,rest,,,,,,,,,
Conditioning,0,0,Intervals,,Intervals,conditioning,required,,ON interval,4,,120,2 min jog
,,1,Hills,,Hill sprints,conditioning,alternative,hills,Hill sprint,7,,20,Walk down
,,1,,,Deadmill,conditioning,alternative,hills,Deadmill push,7,,25,
```

```
test,unit,measurement,attempts,aggregation,better,min,max,milestone_track,baseline_week,retest_weeks
10 m sprint,s,time,3,best,lower,1,4,Speed,1,2
```

## What isn't imported

- Anything after an error: fix the errors (in the page's text boxes, or in
  the spreadsheet and upload again) and check again.
- Unknown columns (listed as warnings).
- Player data, logs and results: an import is a programme definition only.
- Images and files: put links in `session_video` / `exercise_video`, or add
  an attachment link to a session in the builder.

An arbitrary spreadsheet won't import as it is: it needs these columns.
