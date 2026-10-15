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
