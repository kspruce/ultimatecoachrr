# Herd 2027/28: content review (cards, drills, handbook)

Work in progress. This file is the handover: it says what is done and what is next, so any session can carry on from the branch.

## Status

| Part | State |
| --- | --- |
| 1. Coverage and progression | Done |
| 2. One language | Done |
| 3. Timing (release calendar) | Done |
| 4. Better drills | Half done: the plan's own notes are in; hand-written gaps are next |
| 5. Handbook and guide | Not started |

Baseline before any change: `python -m pytest tests -q` gave 834 passed, 20 skipped.

## How the drill files are built

`imports/drills/tools/` holds the scripts that write `herd-drills.json` and `grut-drills.json`. Run from the repo root:

```
python imports/drills/tools/build_drills.py imports/drills/tools            # report only
python imports/drills/tools/build_drills.py imports/drills/tools --write    # write the files
```

- `newdrills.py`: the new library entries (`NEW`), used only the first time an entry is added (after that, edit the JSON or `enrich.py`), and the plan cells renamed so they link to a drill (`RENAMES`).
- `enrich.py`: hand-written harder, easier, 1s and 2s, and Ask lines for drills the plan's notes don't cover (`ENRICH`, keyed by drill title).
- `build_drills.py`: adds the new entries, then for every drill writes the Serves line (problem area and phase), the weeks the plan really uses it, and the harder, easier and Ask lines it finds in the session tabs' notes. It is safe to run again.

The report lists drills still missing a Harder, Easier or Ask section (`no_harder`, `no_easier`, `no_ask`).

## Part 1: coverage and progression

### Drills (done)

- **The gap:** the session tables named about 150 activities with no library entry, so those activities had no drill page behind them. The library had 106 Herd drills; it now has 223, plus the 9 GRUT drills.
- **Added:** 117 entries, each under the name the session table uses. Their "How it runs" restates the plan's own row. Where the plan only names a drill, the entry says so and points to its source.
- **Merged, by renaming the plan cell so it links to a drill that already exists:**
  - "H cut drill" and "Throwing under a mark at stall 6" are now Throwing under pressure.
  - "Triangle mark and hard force" is Triangle forcing in fours.
  - "Ho and dominator in full", "Vert in full", "Pull-play 5-pull" and "Arrowhead as a preview, 5-pull" are 5-pull.
  - "Basic Bull zone walk-through" and "Basic Bull zone, 8-pull" are Bull zone walk-through and 8-pull zone reps.
  - "Bucket swings" is Bucket and swing.
  - "Marked cutting, 2v2" is Cut families with a defender.
  - "Vert deep-cut pull play" is Vert pull play.
  - The two wind-throwing blocks in week 30 are Throwing in the wind.
  - "Throwing in pairs and the 4v3 mini" is the 4v3 mini.
  - "Defending the line and Hollywood squares" is Hollywood squares, which was unused before.
  - "Mid-season skill tests" and "Final skill tests" are Skill test stations.
- **Every library drill is now used** by a session table except 70-pass, which says it is the Phase 1 home throwing set and an option for focused throwing.
- **Still not linked, on purpose:** 113 activities that are meetings, briefings, walk-throughs of game plans, review fixes chosen on the day, and the step-up camp blocks.

### Cards (done)

- **New Card 50, "Your tests and your focus"** (Start here, week 6). No card covered Principle 4 (everyone is measured on improvement): the four skill tests, the mini-tests, the development focus, the skill floor and mentor pairs. It goes out before the first mini-test because weeks 1 to 5 already have two new cards each.
- **New Card 51, "Tempo: choose the pace on purpose"** (Compete, week 34). The plan teaches tempo in week 34 and game management in Phases 3-4, and no card covered either. Week 34 had no new card.
- **Card 15** now names the three cut families (explosion, commitment, shoulder) in the plan's words. The plan, the five-cone drill and the card's own "At training" line use them, but the card never said what they were.
- **Card 1** call table: Jedi added, and Mac and Dynamic dump reworded to match the plan's shared vocabulary. The old Dynamic dump line said "caught on the closed side that flows to the break side", which are the same side.
- **Nothing cut or merged.** The follow-up cards (8, 13, 16, 25, 28, 38) repeat their parent cards on purpose.
- **Looked at and left:** "throwing tired and quick release after the catch" (Phase 2 throwing base) has no card of its own. Cards 8, 26 and 32 cover quick releases, and weeks 14 and 22 already have two new cards each.

## Part 2: one language (done)

**Terms fixed**

| Was | Now | Where |
| --- | --- | --- |
| "match defence", "match D", "switch to match" | person defence, person D | Card 31; Season plan (CRUMBLE); Phase 1 and 2 sessions |
| "benchmark", "benchmarks", "benchmark tests" | skill tests (or "the hucking alley test") | Cards 10 and 14, the release calendar, two drills, the Drills tab, three handbook pages |
| "closed side" | break side | Card 22; Phase 1 and 2 sessions. The glossary still gives "closed side" as another name |
| Dynamic dump "caught on the closed side that flows to the break side" | "caught on the break side that starts quick flow there" (the Season plan's wording) | Card 1; Phase 1 sessions, twice |
| Problem areas named three ways | The pitch's four names: getting open, seeing the field, breaking the mark, keeping the disc | Card release lines ("2028 priority: ..."); the drill library's focus areas; the Season plan's curriculum rows now read "Getting open (cutting under pressure)", "Seeing the field (reading the pitch)", "Keeping the disc (retention)" |

**Glossary:** 32 entries added for words the cards and drills use without explaining: disc line; active, inactive and ready space; negative and positive; dynamic dump; Jedi; threat position; mac; zip; cut families; peppermill; bucket, controller and crash; "Endzone" and "Spread"; triangle, flat and extended mark; force middle; back shoulder; heads-up D; Bull zone; arrowhead; CRUMBLE; buzz switch; the four problem areas; skill tests and mini-tests; development focus; skill floor; mentor pair; skill lead; sideline buddy; 4v3 mini; 5-pull and 8-pull; the three handling rules; Plans A, B and C. "Dump or reset" now matches Card 1 ("any pass behind the disc line").

**Left alone:** "field" and "pitch" are both used everywhere (the pitch itself says "seeing the field"), and "horo", "ho" and "horizontal stack" are all in the glossary.

## Part 3: timing (done)

Every card's Release line was checked against the release calendar (they now agree for all 51 cards) and against the week the rebuilt sessions teach it. No week has more than two new cards.

**Release weeks changed**

- **Card 12, Throwing in the wind: week 26 to week 21.** Wind is trained in week 25 and goes into home throwing from week 23, so week 26 (Tour 1 itself) was after the teaching. Weeks 22 to 25 already have two new cards each. Re-shared in weeks 25, 26 and 30.
- **Card 50** goes out in week 6 and is re-shared in weeks 17, 25 and 35. **Card 51** goes out in week 34.
- **Card 22, Resets,** is re-shared in week 36, when the Jedi lanes game is played.

**"At training" lines rewritten to match the rebuilt sessions:** Cards 4, 5 (unchanged, checked), 6, 7, 9, 12, 14, 15, 19, 24, 25, 27, 33, 35, 39 and 43. Examples: Card 14 sent players to "ladders and Hollywood squares" in week 4, which the session no longer has; Card 15 put 1v1 "name your cut" in week 5 when it is in week 4; Card 6 named a lead-pass drill the joint session has replaced with the GRUT one.

**Calendar themes:** weeks 6, 18, 25, 35 and 36 reworded to match the Weekly plan.

## Part 4: better drills (half done)

Every drill now has a Serves line and the correct weeks. Harder, Easier and Ask lines from the session tabs are in. Still to write by hand in `enrich.py`: about 65 drills with no Harder or Easier, and about 75 with no Ask.

## Tests changed

- `tests/test_theory_import.py`: the cards file now has 51 cards, so the expected card numbers per section, the counts (52 became 54, which includes the three notes) and the last card in Compete were updated.

## Needs a coach's decision

- **Card 43 (force middle, anti-huck force, no-hammer mark) is not taught in any session.** The card used to name two drills in the 1s' week 33 split that the session tables don't have. It now says these are 1s options the captains call in a scrimmage. Either add a 20-minute block to a 1s split (week 33 or 39), or accept it as reading only.

- The Season plan's curriculum rows now lead with the pitch's names for the problem areas. The pitch, Goals and Principles are untouched. Say if you would rather keep the old row names.

- Card 50 goes out in week 6. If you want it before the October tests, a week 1 or 2 card has to move, because those weeks already have two.

- Drills marked "The plan gives this in outline" need their full version checked against the source (the OneNote notebook and the Flik, DK and Hildo material are not in the repo).
