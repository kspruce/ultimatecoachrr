# Herd 2027/28: summary of the work

The season plan export, the session plans and a new full-season S&C programme are ready for the captains to check. Two things are not settled: no 2028 event dates are published yet, and the Gym track's exercises need checking against the Flik Level 2 sheets, which are not in the repo.

- `review.md`: 19 ranked findings.
- `decisions.md`: 17 decisions, each with a recommendation.
- Branch: `claude/vigilant-cerf-305evz`. The brief named `claude/great-ride-ne63b3`, but this session could only push to its own branch.

## What changed in each part

### 1. Review

`docs/herd-2027-28/review.md` checks all eleven tabs against the pitch, Goals and Principles. Each finding says where it is, what is wrong, which goal it hurts, the fix, and whether the fix was made or needs a decision.

### 2. S&C programme

`imports/programmes/thundering-herd-2027-28/` holds `programme.csv` (2,141 rows), `tests.csv` (12 tests) and `build_programme.py`, which wrote them.

- **Four tracks, each running plan weeks 1-51,** so programme week N is plan week N. Start date: 4 October 2027.
- **Home strength (everyone):** two sessions of 20-25 minutes. Phase 1 teaches the positions and held landings. Jumps start in week 14 at 40 contacts and reach 100 in weeks 40, 46 and 47.
- **Gym (optional):** off-season 1 and 2, pre-season 1 and 2, in-season, peak. It replaces the strength block of Home strength A.
- **Throwing:** two 15-minute sessions from the plan's phase menu, plus a third chosen from four focus sessions to match the player's development focus.
- **Speed (optional):** included because the sessions have no progressive sprinting and Trial 1 tests a 50 m sprint. It is 15-20 minutes a week before the season and three or four sprints a week in season.
- **Calendar:** event weeks and Trial 1 are deloads, week 44 is recovery, weeks 45-47 the peak, 48-49 the taper, week 50 rest.
- **Tests:** the filmed 5-10-5 in weeks 1, 18, 35 and 51; the 50 m sprint with splits and the arrowhead agility test in week 18. I also added the four skill tests on their test weeks (see D15).
- **Plan updated:** the Season plan's fitness and home-throwing sections now point to the programme and agree with it.

### 3. Session plans

- **Split sessions rebuilt** on the plan's own shape: throwing, a game, one drill, the game again and harder, 4v4, a toolkit game, a scrimmage. Drills fall from about half of split time to about a fifth.
- **Every week lists** what each game's rules push players to do, why, and a question to ask.
- **Tests have timed rows:** the four full rounds, all eight mini-tests, and one written protocol per skill test (Phase 1 tab).
- **Development-focus time** is the last five minutes of focused throwing until week 24, then the skill floor.
- **The 2s:** every cell names a game and its rule; every scrimmage names one of three handling rules; the step-up camp is four full sessions.
- **Calendar and load:** week 30 is light for the 1s; event and taper weeks have timed tables with their length; there is a review after every event; wind is trained before Tour 1; repeated sprints build from week 21; the joint session has no consequences.
- **New games:** 13 Herd games are described in full in the Drills tab and added to `imports/drills/herd-drills.json`.

**Changed in the plan that you should know about:**

- Mini-tests are 20 minutes, not 10. Two full tests don't fit in 10 (D10).
- Get 10 is run against both forces.
- Phase 4 and 5 sessions state shorter lengths (2.5 to 2.75 hours) where the plan said "shorter and sharper".

**Not changed:** the pitch, Goals and Principles; the weekly themes (apart from naming the Jedi lanes game in week 36 and the step-up camp numbering); the open questions; the captains' and coaches' guide; the theory cards and the handbook.

### 4. Decisions

`docs/herd-2027-28/decisions.md` answers the nine open questions and eight more that came out of the review. The trial criteria and the pathway are built on the four skill tests.

## The five most important review findings

1. **Split sessions were mostly drills:** 45-67% of the session against a principle of 20-30%. Fixed.
2. **The test rounds didn't fit their slots,** so they couldn't give reliable evidence of improvement: 30-40 minutes for 40 players, and mini-tests that were only a line in the notes. Fixed.
3. **Getting open had no pressure phase:** taught in weeks 4-6, then never against a defender in a joint session. Partly fixed in the splits; a theme change needs you (D11).
4. **"Every 2s player handles" had two sessions of support and no measure.** Rules added to every 2s scrimmage; the definition needs you (D12).
5. **Sprint and jump load arrived all at once in weeks 45-46.** Now built up from week 1 in the programme and from week 21 in sessions.

## Decisions waiting on the captains

- **D1** 2028 dates: none published. Every "~" date is a weekday in 2028, so each event could be a week earlier than the plan assumes.
- **D2** Trial selection criteria.
- **D3** Pathway criteria and review windows.
- **D4** Skill leads and the stats and video lead, by the end of August 2027.
- **D5** Guest coaches and their blocks.
- **D6** How the captains share planning.
- **D7** GRUT game clips.
- **D8** The 2s' target events.
- **D9** OneNote material.
- **D10** Get 10 scoring and the 20-minute mini-test.
- **D11** A joint week for getting open under pressure.
- **D12** What "handles in games" means.
- **D13** When the 2s' awards happen.
- **D14** Which days the two sessions are on.
- **D15** Skill tests in the app; a 50 m sprint retest.
- **D16** Two key games that are never played.
- **D17** Who checks and publishes the home programme.

## What I couldn't do, and why

- **2028 event dates:** UKU and the EUF have published nothing for 2028. No date was changed. Sources are cited in D1.
- **Flik Level 2 gym content:** the notebook isn't in the repo. The Gym track follows the block names the plan cites and reuses last season's exercises.
- **Rules for a few named games:** the plan names some Flik and SP games without rules (the Sideways game, the tram-line game, the sideline-start game). I wrote Herd versions and marked them "Plan" (D9).
- **Training days:** the plan doesn't state them, so the programme gives rules, not days (D14).
- **Importer limits** (no app code changed):
  - Programme log fields can't hold a throw count, so it goes in the notes.
  - Alternatives can't span tracks, so "gym instead of home strength" is an instruction, not something the dashboard understands.
  - A split table gives both squads the same length, so the 1s' short sessions in weeks 30 and 48 end with a "Finish" row.

## How I checked the work

- **Parsers:** `parse_export` on the edited export returns no skipped rows and no warnings (51 weeks, 49 session notes, 15 milestones, 12 classroom sessions). `programme_import.parse` on the new programme returns no errors and no warnings.
- **Tests:** the full suite was run at the start, and again after the last change (result in the chat message).
- **Tests I changed:**
  - `tests/test_season_sessions.py`: the "week with no session table" example was week 37, which now has a timed light session. It uses week 50 (rest) and also checks that week 37 builds a 90-minute session.
  - `tests/test_programmes.py`: one new test that the 2027/28 programme imports with no warnings and lines up with the plan's calendar.
- **A failure that isn't from this work:** `tests/test_coach_summary.py::test_something_new_is_sent_and_marked` fails when the suite runs between 22:00 and midnight UTC, because it adds two hours to the real clock.
- **Drill share:** a script counted drill and game minutes in every timed table before and after. After the rewrite, full joint sessions average 15-22% by phase and full splits about 21%.
- **Table times:** every timed table was checked for times in order, and each phase was checked against the review list after it was rewritten.
- **Drill links:** the plan's activities were matched against the drill library with the app's own matcher. Two library drills are unused (70-pass, now home throwing, and Hollywood squares), the same number as before.
