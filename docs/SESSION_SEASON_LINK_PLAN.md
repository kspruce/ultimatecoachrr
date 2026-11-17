# Linking session plans and the season plan: plan

**Question:** can a session and its week in the season plan be linked, so
that a change in either one shows up in the other?

**Answer:** yes, and it's not too difficult. The trick is to avoid a naive
"copy everything both ways". Instead, give every piece of a session one
owner. Notice when the other side has also changed it, and keep the coach's
edit rather than overwriting it.

This also simplifies step 2 of
[SEASON_PLANNING_2028_PLAN.md](SEASON_PLANNING_2028_PLAN.md). The site
already has a good session editor: the session planner, with blocks, a drill
picker, templates, "Copy last week" and Publish. So the season plan should
use that editor rather than gain a second one.

## How it works today

- **One way only.** "Build sessions" turns a week's session notes
  (markdown tables) into sessions. From then on, every save of the week, and
  every re-import, rewrites the session's title, date, aim, notes and blocks
  (`build_sessions` in `app/utils/season_sessions.py`).
- **Coach edits are lost without warning.** If a coach edits a built session
  in the planner (`training.plan`), the next save of that week replaces
  their edits. A banner warns them, but nothing stops it.
- **Rebuilding throws away block links.** `_sync_components` deletes and
  recreates every block when anything differs, so links from the playbook to
  those blocks are lost. The planner's `save_blocks` updates blocks in place.
- **The week can only point at one session.** `SeasonWeek.session_plan_id`
  links one session per week (the joint one), even when the week has 1s and
  2s sessions too.

## The design

### 1. One owner for each piece of a session

| Part | Owner | Notes |
| --- | --- | --- |
| Week number, phase, block, week commencing | Season plan | Always flows from plan to session. |
| Aim, learning points | Season plan | Flows to the session unless a coach overrides it in the planner. |
| Title, focus | Season plan | Same: the plan sets them, and a coach's change in the planner is kept. |
| Date, times, place | Training schedule, else plan | As today. |
| **Blocks** (the activities) | **Both** | Two-way: see sections 2 and 3. |
| Session notes | Both | Two-way, the same way as blocks. |
| Published, cancelled, register, RSVPs, review notes | Session | The plan never touches these (as today). |

### 2. Remember what the plan last wrote

Add `SessionPlan.plan_snapshot` (JSON): a fingerprint of each part as the
plan last wrote it (`blocks`, `title`, `focus`, `aim`, `notes`, `when`).

When the plan builds or updates a session, it checks each part in turn:

| Session still matches the snapshot? | Plan's new version differs? | Result |
| --- | --- | --- |
| Yes | Yes | Update it (as today). |
| Yes | No | Nothing to do. |
| No (a coach edited it) | No | Keep the coach's edit. |
| No | Yes | **Conflict.** Keep the coach's edit, and list it on the week and in the build report: "Week 7, 1s: changed in the session and in the plan." Offer **Use the plan's version** and **Keep the session's**. |

This is a three-way comparison for each part of a session, not for each
character, so it stays simple. It also makes re-importing a spreadsheet
safe.

**Plans built before this change** have no snapshot. On their first sync,
any session that differs from what the plan would write is treated as a
coach edit: it's kept and reported, never overwritten.

### 3. Session to plan: writing back

When a coach saves a built session in the planner:

1. The session's blocks are saved, as today.
2. The week's session notes are written again from all of that week's
   sessions. This uses the step 0 renderer from the 2028 plan:
   - The joint session becomes the joint table.
   - Squad sessions become the split table when their rows line up, or a
     table per squad when they don't. That needs a small parser change: a
     table labelled with a squad's name (**1s session**) is that squad's.
   - The session notes become the week's notes, and learning points come
     from the session.
3. The snapshot is set to the result, so the next build sees nothing new and
   doesn't loop.

This way the week page, the export and the spreadsheet always match the
sessions.

**Deleting a built session** asks "Also remove it from week 7 of the
plan?". If yes, that squad's table is removed from the week, so the next
build doesn't bring the session back. If no, the session stays deleted and
the week shows "1s session deleted. Build again?".

### 4. One editor: the session planner

- **The week page shows its sessions.** For each session: its blocks,
  minutes and linked drills, and its status (draft, published, cancelled,
  register taken). Each has an **Edit in planner** button. The markdown
  textarea moves to an "Edit as text" tab for coaches who prefer it and for
  pasting. Saving it goes through the rules in section 2.
- **The planner shows the plan.** It gets a header with the week, theme,
  phase and block, a link back to the week, and the week's learning points.
  It already finds the week (`_season_week`). The "Built from the season
  plan, edit it there" banner changes to "Linked to week 7. Changes here
  update the plan".
- **Plan weeks without a session yet.** A new **Create draft sessions** button
  makes unpublished sessions for every week with a theme, even if there are
  no session notes yet. They're titled from the theme, start from the plan's
  standard session shape (2028 plan, step 4) or a saved template, and are
  edited in the planner. Players don't see a plan until it's published, as
  today.
- **Schedule dates made later.** A training schedule may make a date that
  falls in a week already holding a draft session for the same squads. That
  date then takes over the draft (its blocks, notes and plan link) instead
  of making a second session. Today the matching only happens when the plan
  builds (`_scheduled_date`). It also needs doing when the schedule makes
  dates (`schedules.sync_schedule`).
- **Every session in a week.** Replace the single `session_plan_id` with a
  week's sessions found by their `external_id` prefix
  (`plan-<season>-wNN-`). That's already unique for each squad. Keep
  `session_plan_id` only for a coach's own hand-picked session.

### 5. Smaller fixes along the way

- `_sync_components` should update blocks in place, matched by position and
  title, like `save_blocks`. Then playbook links and block ids survive a
  rebuild.
- Change a plan-owned field in the planner (such as the title) and the
  planner shows "Changed from the plan · Reset".
- If two coaches edit at the same time, the later save wins for each part.
  The snapshot means the plan side is never silently lost: it shows up as a
  conflict.

## Order of work

| Step | What | Depends on | Size |
| --- | --- | --- | --- |
| A | Snapshot, the three-way rules and the conflict list; blocks updated in place. **This alone stops coach edits being lost.** | — | 2–3 days |
| B | The week page shows its sessions with "Edit in planner"; the planner shows the week. | A | 2 days |
| C | Write-back from planner to week notes; per-squad tables in the parser; deleting asks about the plan. | A, and step 0 of the 2028 plan | 2–3 days |
| D | Create draft sessions for every week; schedule dates take over drafts. | A | 2 days |

That's about 8–10 days in total. Doing this replaces most of step 2 of the
2028 plan: the structured editor on the week page, estimated at 4–5 days.
Only the "Apply to weeks X to Y" and "Copy from week N" buttons are left,
and those can live in the planner, which already copies from a recent
session. So the net cost is about 4–5 days more than the 2028 plan alone.

A suggested combined order:

1. 2028 step 0 (the notes renderer).
2. Link step A.
3. 2028 step 1 (start next season from this one).
4. Link steps B and C.
5. 2028 step 3 (the season grid).
6. Link step D, then 2028 step 4 (generated outlines). D gives generated
   outlines somewhere to live from day one.

## Tests to write

- Three-way rules: for each part, an untouched session is updated, an
  edited one is kept, and a conflict is reported. A plan with no snapshot
  never overwrites.
- Round trip: edit blocks in the planner, and the week's notes change;
  building again reports "up to date" for that session.
- A split week where the 1s and 2s sessions have different rows writes
  per-squad tables, and they parse back to the same sessions.
- Deleting with "also remove from the plan" doesn't come back on the next
  build.
- A schedule date in a week with a draft takes it over; RSVPs and the
  register are untouched.
- Playbook links on blocks survive a rebuild.

## Decisions for you

1. **When both sides change the same session, who wins by default?**
   Suggestion: the session, because it's closer to the day and a coach
   chose it, with the plan's version one click away.
2. **Should title and focus follow the plan?** Suggestion: yes, until a
   coach changes them in the planner.
3. **Should "Create draft sessions" run when a plan is created?**
   Suggestion: no. Make it a button, so the sessions list doesn't fill with
   40 weeks of drafts until a coach wants them.
