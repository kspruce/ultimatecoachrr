# Playbook: drawn, animated plays

Plan for letting coaches draw plays and team concepts (formations) in the
site, with the same editor as the drill drawer, and play them back as
animations. Not built yet.

## Where the playbook is today

- **Diagrams live elsewhere.** A play has an `ultiplay_embed` (a third-party
  iframe) and an `image_url` (an ImgBB link); a formation has
  `ultiplay_embed` and `imgur_url`. Nothing is drawn in the app, so a
  diagram breaks if the other site changes or deletes it, can't be edited
  here, and the PDF export can only show the static image (or a QR code for
  the embed).
- **Formations and plays don't share positions.** A play links to a
  formation, but the play's diagram has to redraw the starting positions by
  hand.
- **Assignments are free text.** `PlayAssignment` says what a position does,
  but nothing ties it to a player on a diagram.
- **Small issues found on the way** (worth fixing alongside):
  - `PlayTag.name` is `unique=True` across all teams, so two teams can't both
    have a "Zone" tag. It should be unique per `team_organization_id`.
  - `PlayForm.__init__` fills its choices from every team's formations and
    tags. The routes overwrite them with the team's own, but the form
    shouldn't query unscoped in the first place.
  - Play routes are `@admin_required`, the drill editor is
    `@coach_required`. Decide which one drawing plays needs (probably coach).

## What the drill drawer already gives us

- `app/static/js/drill_diagram.js` (`window.DrillDiagram`): field drawing,
  players, disc, cones, arrows (`HerdLine`), stages, `movements()` and
  `transitionPlan()` (arrows from a player move them in the next stage),
  `createPlayer()` for playback, PNG/SVG/video export, portrait view on
  phones. Nothing in it is drill-specific.
- `app/static/js/drill_editor.js`: the editor UI. The canvas, tools, stages,
  undo and formation presets are generic. Only a few things are tied to
  drills: `#drill-data` (create/update URLs), `drillDetails()` (title,
  setup, skill level and so on), and the save handler's response handling.
- `app/static/js/drill_viewer.js`: the read-only animation on the drill page.
- `app/routes/session.py`: `_save_editor_diagram()` checks and stores a PNG
  and an SVG per stage, plus the editor JSON on the first stage, in
  `DrillDiagram` rows (base64 in the DB, since Railway wipes the disk).

So most of the work is making the editor reusable and adding storage for
plays. The drawing and animation code is already there.

## Plan

### Phase 1: make the editor reusable (no visible change)

1. Split `drill_editor.js` into:
   - `diagram_editor.js`: everything generic, behind
     `DiagramEditor.init({dataEl, collectDetails, applyDetails, onSaved, presets})`.
   - `drill_editor.js`: a thin wrapper that passes the drill's
     `collectDetails` (today's `drillDetails()`) and its save messages.
2. Move the editor page layout (toolbar, canvas, stage strip, stage notes)
   into a Jinja partial, `templates/_diagram_editor.html`, with a block for
   the details sidebar. `session/drills/editor.html` then just fills in the
   drill fields.
3. Make `drill_viewer.js` generic (`diagram_viewer.js`): it reads any
   `[data-diagram-animation]` element and its JSON, so one page can show
   several animations (the playbook index).
4. Move the checks and storage in `_save_editor_diagram()` into
   `app/utils/diagram_store.py`, taking the owner and the diagram model, so
   drills and plays share the size limits, PNG check and hashing.

`tests/test_drill_editor.py` and `tests/test_drill_editor_browser.py` must
still pass unchanged. They are what tells us the refactor is safe.

### Phase 2: storage and routes for plays and formations

1. New model `PlaybookDiagram`, the same shape as `DrillDiagram` (`order`,
   `step_label`, `caption`, `image_data/mime/hash`, `svg_data/hash`,
   `editor_json`, `team_organization_id`), with `play_id` **or**
   `formation_id` (a check constraint makes sure exactly one is set) and a
   delete-orphan cascade from each. Keep it a separate table instead of
   making `DrillDiagram` polymorphic: `saved_drill_id` is non-null, and the
   season import relies on how those rows behave.
2. Migration for the table (plus the per-team `PlayTag` uniqueness fix).
3. Routes in `app/routes/playbook.py`:
   - `GET /playbook/plays/editor`, `GET /playbook/plays/<id>/editor`
   - `GET /playbook/formations/editor`, `GET /playbook/formations/<id>/editor`
   - `POST /playbook/api/plays`, `POST /playbook/api/plays/<id>` (and the
     same for formations), in the drill API's multipart format
     (`data`, `diagram[]`, `svg[]`, `stage_name[]`, `stage_notes[]`, `editor`)
   - Image and SVG routes. **Unlike drill images, these need a login and the
     right team:** a playbook is more private than a drill library, and
     plays have no guest share links. The PDF export (Playwright, with
     `block_private_requests`) should get the images as data URIs, not
     fetch them.
4. All queries scoped by `get_current_team_id()`; add cases to
   `tests/test_team_isolation.py`.

### Phase 3: the play editor

The details sidebar has the play fields: name, offense/defense, formation,
tags, description, notes, sort order. The old Ultiplay and image-link fields
go under "Legacy diagram" so existing plays keep working.

Play-specific behaviour on top of the shared editor:

- **Start from a formation.** Choosing a formation that has a drawing copies
  its objects into Stage 1, keeping their `herdId`s so they animate. The
  presets dropdown (vertical, horizontal, zone, endzone) also lists the
  team's own formations. It's a copy: editing the formation later doesn't
  change existing plays. Offer "Reset Stage 1 to formation" for that case.
- **Stages as beats.** Suggest names like Set-up, Initiation, First look,
  Continuation, Reset when adding a stage. Each stage's notes become the
  caption in playback and in the PDF.
- **Position labels.** The label picker offers the team's `PlayerPosition`
  names (H1, H2, C1…) as well as free text, so a player on the field and a
  `PlayAssignment` row can match by label.
- **Show or hide defence** for plays where the D is only for context.

Formations use the same editor with one stage, no arrows needed, and the
formation fields in the sidebar.

### Phase 4: viewing

- **Play page** (`play_detail.html`): the animated diagram first (play,
  pause, step back and forward, speed, scrubber, as on the drill page).
  Below it, the stages as small static SVGs with their notes, for reading
  without playing. Order of preference: drawn diagram, then `image_url`,
  then the Ultiplay embed.
- **Position view** (`position_view.html`): pick a position and its player
  and arrows are highlighted in the animation (others faded), next to that
  position's instructions.
- **Playbook index**: each card shows Stage 1's SVG, and tapping it plays the
  animation inline (one viewer per card, made only when tapped, so a long
  playbook stays fast).
- **Huddle mode**: a full-screen, landscape view with large step buttons and
  swiping between plays, for showing on a phone or tablet at the field.
- **Share as video**: `drill_diagram.js` can already record a stage
  animation to a video file, so offer it on the play page for Discord or
  group chats.

### Phase 5: PDF export and sessions

- `app/utils/playbook_export.py`: show a drawn play as its stages side by
  side (2–4 per row) with captions, plus a QR code to the animated page.
  Add the diagram hashes to `cache_key()` so a redraw clears the cached PDF.
- Session builder: a session component linked to plays (via
  `play_session_component`) shows the play's animation, like drills do.

### Later

- Options or branches in a play (for example "if the dump is fronted, go to
  stage 3b").
- Importing an Ultiplays play automatically, if they offer an export
  format; otherwise coaches redraw them.
- Linking clips from the clip library to a play ("here's us running it").

## Tests

- Unit tests mirroring `test_drill_editor.py`: create and update a play and a
  formation, stage count and size limits, non-PNG uploads rejected, editor
  JSON round-trips, images need a login and the right team.
- A browser test mirroring `test_drill_editor_browser.py`: make a
  formation, start a play from it, draw a cut, add a stage, save, and check
  the play page animates.
- PDF export test for a drawn play (stages appear, cache key changes on
  redraw).

## Suggested order

Phase 1 → 2 → 3 (plays first, then formations) → 4 (play page first) → 5.
Phases 1–3 together are the smallest useful release: coaches can draw an
animated play and watch it on its page. Everything after that improves how
plays are shown and shared.
