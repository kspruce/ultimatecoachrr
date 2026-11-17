# Season planning for 2028: plan

Goal: a coach can get from "new season" to "every week has a session I'm
happy with" in an evening, not a weekend. That applies whether the team is
new or returning.

This builds on what's already there. See [SEASON_PLAN.md](SEASON_PLAN.md):
the starter templates, the week editor's markdown session notes,
`parse_week_notes`, `match_drill`, Build sessions, and the spreadsheet
import and export.

## What changed from the first list

| First idea | Change | Why |
| --- | --- | --- |
| 1. Templates write session outlines | Kept, but moved to step 4. The "standard shape" becomes a plan setting, not part of the template. Generated outlines are marked **draft** until a coach touches them. | Generating outlines needs the same row model as the editor, so the editor comes first. Drafts must not sync to players' sessions. |
| 1. Link to matching drills | Templates name drills explicitly (by standard card), with a theme-to-focus-area fallback. Unmatched rows show "pick a drill". | Themes like "Cutting: timing, under and away" never match a drill title, so `match_drill` alone would link almost nothing. |
| 2. Structured editor | Kept, and promoted to the foundation. It now covers split (per-squad) tables and learning points. A raw-markdown tab stays for anything else. It's gated on round-trip tests against a real season's notes. | The current parser reads more than "time, activity, notes". An editor that silently drops a Source column or a split table loses work. |
| 2. Time *or* duration | The coach types durations; clock times are worked out from the plan's training start time and written to the markdown. | The parser needs clock times, but coaches think in minutes. |
| 2. Apply to weeks X to Y | Kept, with a preview. By default it only fills empty weeks. Every overwrite keeps the previous version. | It's the easiest way to wipe ten weeks of work by accident. |
| 3. Season grid + 4. Progress view | **Merged.** Status columns go on the grid, and the gaps list sits above it. | They show the same rows. One page to plan and to check is simpler than two. |
| 3. Insert or remove a week | Kept, and reframed as "insert a break week here". Built sessions' keys get renumbered so RSVPs stay attached. | Session ids contain the week number. A naive shift would delete and recreate sessions. |
| 5. Start next season from this one | **Moved to step 1.** | It's the smallest piece and the biggest win for any team that already has a plan, including ours. |
| 5. Save as a template for other teams | Split. A team-private template ships with step 1. Sharing across teams comes last and goes through admin review. | Plans contain coach notes, names and drill ids that mean nothing to another team. |

## Order of work

### Step 0: session outline model (foundation, no UI)

A small module, `app/utils/session_outline.py`, that turns a week's session
notes into structured rows and back again.

- `Outline`: a list of tables. Each table has a label ("Joint session",
  "Split session"), a length, and a squad or squads. Each row has a start
  time, a duration, an activity, an optional drill id, "how it runs" and a
  source. An outline also holds its learning points and free notes.
- `parse(markdown, squads) -> Outline` reuses the table parsing in
  `parse_week_notes`; don't write a second parser.
  `render(outline, start_time) -> markdown` writes the format the parser
  already reads.
- `Outline.unsupported`: true when the notes hold something the editor
  can't show, such as a second joint table, an odd header or text between
  tables. The editor then opens on the markdown tab.
- **Gate:** a test that runs every week of `docs/herd-2027-28` (and the two
  templates' generated weeks) through parse, render and parse again. Build
  sessions must give the same components either way.

Drill links: the renderer writes the drill's exact library title, so
`match_drill` keeps working. Linking by id instead (`[Title](drill:123)`, so
renaming a drill doesn't break links) is a later parser change. It isn't
needed for the first version.

### Step 1: start next season from this one

**Edit plan > Settings > Start next season from this plan.**

- The form asks for a new season label, a new first week (it defaults to
  52 weeks on, moved to a Monday) and what to copy, with checkboxes.
  - Always copied: phases, weeks (block, themes, session title and session
    notes, event and break flags), milestones, squads, training days and
    times, player access.
  - Ticked by default: pages, classroom sessions (titles, goals, plans and
    prep only).
  - Not ticked by default: coaches' week notes.
  - Never copied: linked sessions (`session_plan_id`), classroom summaries,
    recordings, join links and times, and `sessions_built_at`.
- Phase programmes are kept but flagged, because a calendar programme's
  dates belong to the old year.
- After cloning, a checklist page lists every event and break week with its
  new date: "These moved with the dates. Check they still line up with the
  2028 calendar." This also covers bank holidays and tournament dates that
  don't fall on the same weekday.
- The new plan is a **draft**: it's created but not made current. Players
  keep seeing this season until a coach presses "Make current". This uses
  the existing `make_current`.
- **Save this plan as our template** goes in the same place. It stores a
  team-private template, the same shape as `season_plan_templates.py`, in a
  new `SeasonPlanTemplate` table (team id, name, JSON body). It appears on
  Create a plan next to the built-in ones. Coach notes and classroom
  materials are stripped out.

Tests: dates shift correctly across a year boundary; a season label clash
gives an error; built-session fields are not copied; the old plan is
unchanged.

### Step 2: structured session editor (in Edit week)

This replaces the session notes textarea with rows. The **Markdown** tab
stays as a fallback.

- Each table shows **Duration | Activity (drill picker) | How it runs |
  Source**, with a running clock column worked out from the plan's
  `joint_start` (or `split_start` for split tables).
- A split table has one activity column per plan squad, with a "same as
  first squad" toggle per cell. This writes `Same`, which the parser already
  understands.
- The drill picker searches the team's library and public drills. Picking
  one fills the activity name and the drill's recommended duration.
  Free-text activities are fine too.
- Learning points get their own list field. Everything else goes in "Other
  notes".
- Buttons:
  - **Start from the plan's standard shape** (step 4 adds this; until then,
    from a saved outline).
  - **Copy from week N** shows the other week's outline next to this one
    before copying.
  - **Apply this outline to weeks X to Y** opens a preview that lists each
    week as *empty: will fill* or *has notes: will skip*. A tick box allows
    overwriting. With sessions built, it also shows "N sessions will update".
- **Undo:** add `SeasonWeek.previous_session_md`. It's set on every save
  that changes the notes, and the week page gets a "Restore previous
  version" link. A full history can come later if people use it.
- Saving still writes `session_detail_md` and calls `sync_week`, so Build
  sessions, the import and the export don't change.

Tests: the editor's POST renders the same markdown as a hand-written
fixture; an unsupported week opens on the Markdown tab and saves it
untouched; Apply skips non-empty weeks unless overwrite is ticked.

### Step 3: season grid with progress

**Edit plan > Season grid** (`/season-plan/grid`): one row per week.

- **Editable:** block, theme (joint and one per squad), event, break.
  Changes save per cell, or with one Save button; pick whichever is simpler
  with the current form-post style. Fill-down: select cells, then Ctrl+D or
  a "Fill down" button.
- **Read-only status columns:**
  - Theme ✓.
  - Session notes: none, draft or written.
  - Drills linked, as "4 of 6".
  - Sessions: not built, built, or **out of date**. Out of date means the
    notes changed after the last build. That needs `SeasonWeek.notes_updated_at`.
- **Gaps panel** above the grid, for example "Weeks 7 and 9: no theme" and
  "Weeks 3 to 5: no session". It puts the next four weeks first, and each
  item links to that week's editor.
- **Save and next week** in Edit week returns to the grid's next gap, not
  just to week N+1.
- **Insert a week here / Remove this week:**
  - Week numbers, `week_commencing`, phase week ranges, milestone week
    ranges and classroom sessions move with the shift.
  - Built sessions' `external_id`s and `week_number`s are renamed in place,
    so attendance and RSVPs stay attached.
  - Removing a week that has notes or a built session with RSVPs asks for
    confirmation. A built session with RSVPs is left alone, with the same
    warning `build_sessions` gives today.
  - All of this lives in one function, `build.shift_weeks(plan, at, by)`,
    and is tested on its own.
- Coaches' dashboard nudge: "2 of the next 3 weeks have no session yet",
  linking to the grid.

### Step 4: templates write session outlines

- **Standard session shape** becomes a plan setting: an `Outline` with
  placeholder rows (Warm-up 15, Skill 25, Game 30, Scrimmage 30, Close 5),
  edited with the step 2 editor. It's set when the plan is created, from the
  template's `HOW_WE_TRAIN` or the club's own.
- Each template week can name drills per slot:
  `{'theme': ..., 'drills': {'Skill': 'Box drill', 'Game': '4v4 continuous'}}`.
  - Drill names are resolved against the team's library, then standard
    cards, then public drills, then the theme matched against
    `SavedDrill.focus_area`.
  - A slot with no match says "Pick a drill for: <theme>".
  - Ship a set of standard drill cards that the two built-in templates
    point to, so a new team gets real links.
- When a plan is created from a template, or a coach presses **Generate
  outlines for empty weeks**, each week gets its theme plus the shape plus
  those drills. The week is marked `session_is_draft = True`.
- **Drafts:**
  - Build sessions skips draft weeks (or builds them unpublished, using the
    existing `SessionPlan.is_published`).
  - The grid shows them as "draft". The week page shows "Generated: check
    and save".
  - The first manual save clears the flag.
  - If the theme changes while a week is still a draft, its outline is
    generated again. A week a coach has edited is never overwritten.
- Skip this step for break weeks. Event weeks get the template's light
  session.

### Step 5: share templates between teams

- A team template can be **offered to other teams**. A site admin reviews
  it before it appears in everyone's Create a plan list. It goes out under
  the team's name, or anonymously if the team chooses.
- On export, drill links become titles and a copy of each linked drill is
  included. The receiving team gets those drills added to its library.
- Pages are checked for names before an admin approves.

## Data changes (one migration per step)

| Step | Change |
| --- | --- |
| 1 | `season_plan_template` table (team id, name, hint, body JSON, shared, approved) |
| 2 | `season_week.previous_session_md` |
| 3 | `season_week.notes_updated_at` |
| 4 | `season_plan.standard_shape_md`, `season_week.session_is_draft` |
| 5 | Reuses the `season_plan_template` sharing columns |

## Risks and decisions to make

- **Round-trip fidelity** is the main technical risk. If the herd plan
  doesn't round-trip cleanly, the editor scope shrinks to joint tables, and
  split weeks stay in markdown.
- **Drafts reaching players.** The rule is that nothing generated or
  bulk-applied reaches a published session without a coach saving that
  week, or a preview listing what will change.
- **Week shifting with built sessions.** This needs careful tests, and it
  should probably be blocked for weeks that are already in the past.
- **Decision:** should the clone keep the season's week count, or fit a new
  end date? Suggestion: keep the count, and let Settings change it as it
  does today.
- **Decision:** should team templates be visible to captains, or coaches
  only? Suggestion: coaches only, to match Edit plan.

## Rough size

| Step | Size |
| --- | --- |
| 0. Outline model and round-trip tests | 1–2 days |
| 1. Clone and save as template | 2 days |
| 2. Structured editor | 4–5 days (the biggest, mostly the JS editor) |
| 3. Grid, progress and week shifting | 3–4 days |
| 4. Generated outlines | 2–3 days, plus writing the standard drill cards |
| 5. Cross-team sharing | 2 days |

Steps 0–3 together are enough to plan 2028 comfortably. Step 4 is for new
teams. Step 5 can wait until a few clubs have templates worth sharing.

## Done alongside: browsing a season of sessions

The sessions list (Training → Sessions) now copes with a whole season built
from the plan. It opens on what's coming up, groups sessions by week (with
the plan's week, phase and block), folds all but the nearest weeks, and has
search and a "Go to week" picker. Coaches also see what each session still
needs: no plan yet, not published, or register not taken. Details are in
[SESSIONS.md](SESSIONS.md). Step 3's grid can link each week to
`/sessions/?show=all#week-<monday>`.
