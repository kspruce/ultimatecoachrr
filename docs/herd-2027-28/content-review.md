# Herd 2027/28: content review (cards, drills, handbook)

Work in progress. This file is the handover: it says what is done and what is next, so any session can carry on from the branch.

## Status

| Part | State |
| --- | --- |
| 1. Coverage and progression | Drill library done. Cards: next |
| 2. One language | Not started |
| 3. Timing (release calendar) | Not started |
| 4. Better drills | Half done: the plan's own notes are in; hand-written gaps are next |
| 5. Handbook and guide | Not started |

Baseline before any change: `python -m pytest tests -q` gave 834 passed, 20 skipped.

## How the drill files are built

`imports/drills/tools/` holds the scripts that write `herd-drills.json` and `grut-drills.json`. Run from the repo root:

```
python imports/drills/tools/build_drills.py imports/drills/tools            # report only
python imports/drills/tools/build_drills.py imports/drills/tools --write    # write the files
```

- `newdrills.py`: the new library entries (`NEW`) and the plan cells renamed so they link to a drill (`RENAMES`).
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

### Cards (next)

Planned:

- New Card 50, "Your tests and your development focus" (skill tests, mini-tests, development focus, skill floor, mentor pairs). No card covers Principle 4.
- New Card 51, "Tempo and game management", for week 34. The plan teaches tempo and no card covers it.
- Card 15: name the three cut families (explosion, commitment, shoulder), which the plan and the five-cone drill use.
- Card 1: add Jedi to the call table, to match the plan's shared vocabulary.

## Part 4: better drills (half done)

Every drill now has a Serves line and the correct weeks. Harder, Easier and Ask lines from the session tabs are in. Still to write by hand in `enrich.py`: about 65 drills with no Harder or Easier, and about 75 with no Ask.

## Tests changed

None yet.

## Needs a coach's decision

- Drills marked "The plan gives this in outline" need their full version checked against the source (the OneNote notebook and the Flik, DK and Hildo material are not in the repo).
