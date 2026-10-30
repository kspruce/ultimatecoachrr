# Playbook: what's left

Plays are now drawn in the drill editor and stored as `DrillDiagram` rows
(`play_id`). The playbook overhaul also brought set-ups, roles in drawings,
the role picker on the animation, the PDF with every stage, game-day cards,
call sheets and share links. This plan covers only what is still open.

The main thread running through it: **moving off Ultiplays**. The team has
a large library of plays (and drills) in Ultiplays that will be redrawn by
hand in the editor. The work below makes that redrawing quick, tracks how
far it has got, and then removes Ultiplays embeds from the site.

## 1. Moving off Ultiplays

Where embeds are used today:

- Plays: `Play.ultiplay_embed`, set on the play form
  (`templates/playbook/play_form.html`, `routes/playbook.py` `save_play`)
  and shown on the play page when there's no drawing or picture.
- Drills: `SavedDrill.ultiplay_embed`, set on the drill form and shown in
  the drill list and on the drill page. The drill list also has an
  "Ultiplays" button linking to their site.
- PDF export: `playbook_export._item` uses the embed's URL for the QR code.
  **So a drawn play gets no QR code at all.** It should link to the play
  page (or its share link) instead (see 1.4).
- `Formation.ultiplay_embed`: formations are now in Theory and nothing
  shows this any more.

### 1.1 Get the library into the platform (bulk add)

Many Ultiplays plays may not exist in the playbook yet. Typing them in one
by one before drawing is slow.

- New coach-only page, **Playbook → Import from Ultiplays**: paste a list,
  one per line, as `Name | embed code or ultiplays.com link`, or just links.
- Each line becomes a **draft** play (offence by default, with a per-line
  `O`/`D` option), with the embed stored so it can be copied from. Duplicate
  links or names already in the playbook are skipped and listed.
- The same for drills, from the drill library.
- All of these appear on "Plays to draw" (1.2).

### 1.2 Redraw side by side

`/playbook/redraw` lists what's not drawn yet. Make it the place for
working through the library:

- **Progress:** "34 of 120 drawn" at the top, with filters (offence or
  defence, has an Ultiplays link, draft).
- **Reference panel in the editor:** when a play being drawn has an
  Ultiplays embed or a picture, `play_editor.html` shows it in a panel that
  can be collapsed (on a phone, a "Show original" toggle over the canvas).
  You redraw from it without switching tabs. The panel only reads the old
  field; it never saves it.
- **Save and next:** after saving, a "Next play to draw" button opens the
  next one on the list, so a session of redrawing is one click per play.
- **Stage names from the original:** Ultiplays plays are usually in steps.
  Adding a stage suggests "Step 2", "Step 3" so the stages line up with the
  original while redrawing. (Changing them later is easy.)
- The same reference panel and "next" button for drills: a drill list
  filter for "not drawn yet" and the panel in `session/drills/editor.html`.

### 1.3 Stop adding new embeds

As soon as 1.2 is in:

- Remove the "Ultiplay embed code" field from the play form and the drill
  form for **new** items. On existing ones it stays read-only under
  "Original (Ultiplays)" until they're drawn.
- Remove the "Ultiplays" link button from the drill list.
- Once a play or drill is drawn, the play page stops showing the embed
  (the drawing is shown already; the embed then sits under a collapsed
  "Original" section, so you can check the redraw).

### 1.4 PDF QR codes go to the play

In `playbook_export._item`, the QR code links to the play on this site:
its share link if it has one, otherwise the play page (which needs a
login). Fall back to the Ultiplays URL only while a play isn't drawn.

### 1.5 Remove embeds for good

When "Plays to draw" (and the drill equivalent) shows nothing that still
relies on an embed, or the coaches decide the rest aren't worth redrawing:

- A last check on `/playbook/redraw`: "Clear the Ultiplays links from N
  drawn plays", run by a coach, then a migration that drops
  `play.ultiplay_embed`, `saved_drill.ultiplay_embed` and
  `formation.ultiplay_embed`.
- Remove the `embed_html` uses in the playbook and drill templates,
  `extract_embed_url` in `playbook_export.py`, and the drill form's embed
  script. Check whether anything else still needs `embed_html`
  (`app/utils/media_embed.py`) before removing that too.
- After that, `frame-src https:` in the CSP (`app/__init__.py`) can be
  narrowed to what's actually embedded (clip video hosts).
- Data exports and backups: check they cope with the dropped columns.

Undrawn plays whose only diagram was the embed: before the columns go,
they're either drawn, given a picture, or retired. The clear-up page says
which ones are left.

## 2. Playbook index: play the animation on a card

The index (`_macros.html` `thumb`) shows Stage 1 as a static image.

- Tapping the thumbnail of a play with more than one stage plays it in
  place (play/pause on the card; a tap elsewhere opens the play).
- Make `drill_viewer.js` work on any number of `[data-diagram-animation]`
  elements, and create each viewer only when it's tapped, loading the
  drawing JSON from a small endpoint, so a long playbook doesn't load every
  drawing up front.
- The same on the game-day cards, where it matters most.

## 3. Share a play as a video

`drill_diagram.js` already has `recordVideo` / `videoType`. Add a "Save as
video" button on the play page (and the drill page) that records the
animation to a file to post in Discord or a group chat. Respects the role
picker, so you can send a video of one role's path. Hidden where the
browser can't record (`videoType()` returns nothing).

## 4. Hide the defence during playback

For offence plays where the defenders are only there for context:

- A "Defence" toggle (show / faded / hidden) next to the role picker on the
  play page, cards and share page, using the same `mapObjects` hook as the
  role picker (`player-d` objects and arrows drawn from them).
- The play can save its default (for example "faded") from the editor.

## 5. Plays in sessions

A session component can link plays (`play_session_component`, the
multi-select in `session/component_form.html`), but the session doesn't show
them.

- On the session page and the session script, show each linked play's
  thumbnail, and its animation when tapped (reusing 2).
- Replace the multi-select with the playbook's searchable picker
  (as used for linking theory, drills and clips on a play).

## 6. Image privacy (decide, then maybe change)

Play stages are served by the public drill image route
(`session.drill_diagram_image`), protected by a hash in the URL and cached
as `immutable`. Anyone who has the link can open it, including after a share
link is stopped or a play goes back to draft.

Options:
- **Leave it.** The URL can't be guessed, and share links already use data
  URIs.
- **Team-only for plays:** for a diagram with `play_id`, require a login and
  the play's team, and send `Cache-Control: private`. The share page and the
  PDF already inline the images, so nothing else breaks.

Recommended: team-only. It's a small change in `_get_diagram_or_404` and
the playbook is the team's most private material.

## Later

- Options or branches in a play ("if the dump is fronted, go to stage 3b").

## Suggested order

1. 1.1–1.4 (bulk add, redraw side by side, stop new embeds, QR codes), so
   redrawing the Ultiplays library can start now.
2. 6 (image privacy), as it's small.
3. 2 and 5 (animations on cards and in sessions).
4. 3 and 4 (video, hide the defence).
5. 1.5 once the library has been redrawn.
