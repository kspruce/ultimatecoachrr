# Playbook: what's left

Plays are drawn in the drill editor and stored as `DrillDiagram` rows
(`play_id`). The playbook overhaul brought set-ups, roles in drawings, the
role picker, the PDF with every stage, game-day cards, call sheets and
share links. The items below were the open ones; most are now done.

## Done

- **Play images are for the team only.** `session._get_diagram_or_404`:
  a diagram with a `play_id` needs a signed-in member of the play's team
  (and a coach for a draft), and is cached `private`. Drill diagrams stay
  public for guest share links. Share links and the PDF already put the
  images in the page.
- **PDF QR codes go to the play**: its share link if it has one, else its
  page (`playbook_export.play_url`). An old Ultiplays link is used only
  while the play isn't drawn. The share link is part of the PDF cache key.
- **No new Ultiplays links.** The embed field is gone from the play and
  drill forms. An existing link stays, read-only, as "Original (Ultiplays)"
  with a "Remove the Ultiplays link" tick box. Once something is drawn,
  coaches still see the original in a collapsed section, to check the
  drawing; players don't. The drill library lost its Ultiplays button, and
  shows a drill's drawing before its embed.
- **Bulk add from Ultiplays (temporary)**: Playbook → New play → Add from
  Ultiplays (also on "Plays to draw"). Paste `Name | link or embed code`,
  one per line, for one side at a time. Each becomes a draft keeping its
  link. Links or names already in the playbook are skipped.
- **Play it in place**: tap a drawn play's picture in the playbook list or
  on a session to watch it in a pop-up; "Play it" on a game-day card plays
  it in the card. `play_preview.js` loads fabric and the drawing
  (`/playbook/plays/<id>/drawing.json`) only when tapped.
- **Save as video**: a Video button by the animation on a play's (and a
  drill's) page records what's on screen, with the role picked and the
  defence as chosen. Phones get the share sheet; computers a download.
  Hidden where the browser can't record.
- **Defence shown, faded or hidden**: a picker under the animation when
  the drawing has defenders. Each play has a starting choice
  (`play.defence_view`, set on the play's details once it's drawn), also
  used by the previews. Shared logic: `DrillDiagram.viewObjects`.
- **Plays in sessions**: each part of a session shows its plays (picture,
  call, tap to play; drafts for coaches only), and the session part form
  picks plays from a searchable list instead of a Ctrl-click box.

## Still to do

### Remove Ultiplays for good (when the library is redrawn)

- Clear the remaining links (the "Remove the Ultiplays link" tick box, or
  a one-off clear-up), then a migration dropping `play.ultiplay_embed`,
  `saved_drill.ultiplay_embed` and `formation.ultiplay_embed`.
- Remove the bulk add (`import_ultiplays` in `routes/playbook.py` and
  `templates/playbook/import_ultiplays.html`) and its links.
- Remove the embed display in the play page, drill list and drill page,
  `extract_embed_url` and the Ultiplays fallback in `playbook_export.py`,
  and the `embed_html` filter if nothing else uses it.
- Narrow `frame-src https:` in the CSP (`app/__init__.py`) to what's still
  embedded (clip video hosts).
- Plays whose only diagram was the embed: draw them, give them a picture,
  or retire them first ("Plays to draw" lists them).

### Later

- Options or branches in a play ("if the dump is fronted, go to stage 3b").
- Bulk add for drills, if the drill library needs it too.
