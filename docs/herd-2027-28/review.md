# Herd 2027/28: review of the season plan

This review checks the plan in `imports/season-plan-export/` against its own pitch, Goals and Principles. It covers all eleven tabs. Anything that is fine is left out.

Findings are ranked by how much they matter for the season goals. Each one says where it is, what is wrong, which Herd goal it hurts, the fix, and who makes the fix:

- **Part 3** means the fix is made in the session plans (or another tab) in this branch.
- **Part 2** means the fix is in the new S&C programme.
- **Decision D*n*** means it needs the captains; the recommendation is in `decisions.md` under that number.

**How drill share was counted.** Every timed row in a session table was marked as a game, a drill, or neither (warm-up, water, briefings, tests, the skill floor). Drill share is drill minutes divided by the length of the session (180 minutes unless the plan says otherwise). The counting script is rough at the edges ("drill, then game" rows count as drills), so the numbers are a guide, not a measurement.

## The five that matter most

1. **Split sessions are mostly drills** (finding 1). Principle 2 says 20-30%. Phase 1 splits schedule 80-110 minutes of drills in 180 (45-60%), and Phase 2 splits 90-120 minutes (50-67%).
2. **The tests can't produce the evidence the goals depend on** (findings 2 and 3). Full test rounds are given 30-40 minutes for 40 players, and five of the eight mini-tests are only a line in the notes, not a timed row.
3. **Getting open, the first of last season's four problems, has no Phase 2 week** (finding 4). It is taught in weeks 4-6 and then never meets a defender in a joint session.
4. **The 2s' headline process goal has almost no support** (finding 5). An "everyone handles" rule appears in two 2s sessions all season, and nothing measures it.
5. **Sprint and jump load arrives late and all at once** (finding 6). Repeated sprints and plyometrics first appear in sessions in weeks 45-46, four weeks before Nationals, and 50 m maximal sprints appear cold at Trial 1 and in week 28.

## Findings

### 1. Split sessions run at two to three times the planned drill share

- **Where:** Phase 1-3 session tabs, every split table; Season plan, Weekly structure.
- **What's wrong:** the Weekly structure gives the split theme hour as "game, drill, game". The session tables replace it with two 30-minute drill blocks, and from Phase 2 the 40-minute team-toolkit block is a drill as well. Typical counts in 180 minutes:

  | Sessions | Drill minutes | Share |
  | --- | --- | --- |
  | Joint, Phases 1-2 (standard shape) | 50 | 28% |
  | Joint, weeks 14 and 21 | 90 | 50% |
  | Joint, week 28 (130-minute session) | 45 | 35% |
  | Split, Phase 1 | 80-110 | 45-60% |
  | Split, Phase 2 (weeks 14-23) | 90-120 | 50-67% |
  | Split, Phase 3 (weeks 28, 30, 32-34) | 90-120 | 50-67% |

  The joint sessions sit at the top of the range. The splits, which are half of all training time, do not follow the principle at all.
- **Goal it hurts:** Principle 2 (learn it in the game) and Principle 5 (fun). It also hurts retention of players: the 2s sessions are the most drill-heavy.
- **Fix:** rebuild every split table on the plan's own shape: throwing under pressure (20), theme game (20), one drill (20), the game again and harder (20), 4v4 continuous (20), team toolkit as a short walk-through then a game (40), scrimmage (20). That gives about 50 drill minutes (28%). Swap the drill blocks in joint weeks 14 and 21 for games the club needs anyway.
- **Who:** Part 3.

### 2. Full test rounds don't fit the time they are given

- **Where:** Phase 1 week 1 (five stations of 8 minutes); Phase 2 week 18 (40 minutes, with two extra sprint tests "for anyone new"); Phase 3 week 35 (30 minutes for "the four skill tests for everyone"); Phase 5 week 51 (50 minutes).
- **What's wrong:** the 1v1 cutting test is 10 reps per player. A group of eight needs 80 reps, which is about 13 minutes on three lanes, not 8. Get 10 has to be run on both sides (the "confident break thrower" definition needs both), so it is 20 throws each. Week 35 gives 40 players 30 minutes for all four tests. Rushed tests give noisy scores, and noisy scores can't show whether a player improved.
- **Also:** the test set-up differs between tabs. The Season plan says the cutter starts "from a stack spot 15 m from the thrower"; the Phase 1 kit list says "a 10 x 10 m cone box". The drill library's Baseline tests card lists four stations of 10 minutes and leaves out the 1v1 cutting test.
- **Goal it hurts:** Principle 4 (everyone measured on improvement); the goal "every player improves on 3 of the 4 skill tests"; fair selection; the pathway.
- **Fix:** one written protocol for each test, used at every round. Weeks 1 and 18: three or five stations of 12-15 minutes in the joint session, with the hucking alley and catching tests run at the start of that week's split. Weeks 35 and 51: five stations of 12 minutes (65 minutes with changeovers).
- **Who:** Part 3. Whether Get 10 counts as one score out of 20 or two out of 10 is Decision D10.

### 3. Mini-tests and development-focus time are not in the timed tables

- **Where:** weeks 6, 15, 22, 27, 32, 40 and 45 (mini-test is a line in the notes); week 10 (in the table, but 15 minutes at 1:15 for both tests and the drill); Season plan and Phase 2 intro ("at the end of the warm-up"), week 6 ("from the start of focused throwing").
- **What's wrong:** the app builds sessions from the timed rows, so a mini-test that is only in the notes is not in the session a coach runs from. In weeks 15 and 22 the warm-up row is 20 minutes with no room for 10 more. From week 25 the mini-test "runs at the start of the skill floor", but the skill-floor row still says 12 minutes on each partner's focus, which no longer fits in 25. Week 45 has two mini-tests (joint and 2s split), and week 48 adds a "final mini-test" that is not one of the eight.
- **Goal it hurts:** Principle 4; "progress is visible, not assumed".
- **Fix:** give every mini-test its own timed row (10 minutes straight after the warm-up, with the next block shortened). From week 25, mini-test weeks run 10 minutes of test and 15 of skill floor on one partner's focus, and the other partner's the week after. Call the 2s' week 45 and 48 tests "camp tests" so the count of eight club mini-tests stays true.
- **Who:** Part 3.

### 4. Getting open is taught once and never put under pressure

- **Where:** Season plan, Skills curriculum ("Cutting under pressure"); Weekly plan, Phase 2; Phase 2 review table.
- **What's wrong:** the curriculum promises "beating a tight defender; timing cuts to start before the thrower catches; clearing" in Phase 2. The Phase 2 joint themes are resets, breaking (two weeks), reading the pitch, three trials, retention (two weeks), game day and defence. The Phase 2 review credits cutting to weeks 15, 16 and 21, but those are 1s structures (ho shapes, give-and-go, 3H cuts). The 2s get no cutting under pressure at all. The only pressure on getting open before squads are picked is the trial test itself. Retention, by contrast, gets weeks 14, 21, 22, 27, 36 and 40.
- **Goal it hurts:** the pitch (getting open is the first of last season's four failures); "every player improves on 3 of the 4 skill tests" (the 1v1 cutting test is one of them); the 2s' "win more games".
- **Fix (made):** inside the existing themes, add a getting-open game against a tight defender to weeks 14, 16, 17 and 21 for both squads, and say so in the Phase 2 review. **Fix (needs a decision):** give getting open its own Phase 2 joint week by merging the two retention weeks.
- **Who:** Part 3 for the games; Decision D11 for the theme change.

### 5. "Every 2s player handles" is a goal without sessions or a measure

- **Where:** Season plan, Goals and The 2s (commitment 4); Phase 1 week 1 and week 3 2s splits; every 2s split from week 4.
- **What's wrong:** the rule "last player to touch the disc picks up" appears in week 3, and a stall rule in week 1. No 2s session after week 3 has an everyone-handles rule, although the Weekly structure lists "every player handles" in the 2s toolkit block every week. Nothing counts who handled at events, so nobody can say in September whether the goal was met.
- **Goal it hurts:** the 2s process goal "every 2s player handles in games"; commitment 4.
- **Fix:** a standing, named rule in every 2s scrimmage and toolkit game (it rotates between three rules so it stays fresh), and a "handler tally" line on the 2s' four-number stats sheet.
- **Who:** Part 3 for the session rules. What counts as "handles in games" is Decision D12.

### 6. Sprint and jump load is not built up, then arrives before Nationals

- **Where:** Season plan, Fitness table ("Repeated sprints... Phase 2 onwards, building up"; "Plyometrics... Phases 2-4"); Phase 5 weeks 45 and 46; Phase 2 week 18; Phase 3 week 28.
- **What's wrong:** no split session in Phases 2-4 contains repeated sprints or plyometrics. Both appear for the first time in weeks 45-46, at 10-50 m, four and three weeks before Nationals. Maximal 50 m sprints appear cold twice: the trial sprint test in late January and "one of Hildo's eight sprint rules per 50 m rep" in week 28. The 2025/26 programme stopped after 10-16 weeks, so nothing covers the season.
- **Goal it hurts:** Nationals (hamstring injuries in August cost the peak); fair trials (a sprint test nobody has trained for).
- **Fix:** the new programme has a small Speed track that builds sprint exposure from week 1, tops up weekly in season, and a home plyometric progression from about 40 contacts in week 14 to about 100 in weeks 40 and 46-47. In the sessions, repeated sprints go into the 4v4 conditioning block from week 21 in small doses, so weeks 45-46 are a peak, not an introduction.
- **Who:** Part 2 and Part 3.

### 7. The 2s' sessions are often the 1s' session with a higher stall

- **Where:** 2s column of the split tables. Examples: week 3 "Throwing pairs, catcher calls the catch type" and "Same drill at stall 7"; weeks 4, 9, 10, 28, 30, 32, 33, 34, 38, 39 and 40 end with a bare "Scrimmage"; week 10 "Sideways game" and week 16 "Break inside" have no rules; week 27 "Their top fix from their latest games"; weeks 26, 31, 36 and 41 give the 2s one phrase.
- **What's wrong:** commitment 9 says "every 2s split activity names a specific drill or game with its rules, not a generic 'throwing pairs'". The plan uses those exact words in week 3. Principle 3 says difficulty changes, not content; in most weeks only the stall count changes.
- **Goal it hurts:** the 2s commitments 2, 4 and 9; "win more games than 2026/27, and enjoy it".
- **Fix:** every 2s cell names the game, its rule and how it differs from the 1s (more overload, more touches per player, a longer stall, a handling rule).
- **Who:** Part 3.

### 8. The step-up camp is three short sessions, not four

- **Where:** Season plan, The 2s (commitment 10: "a four-session development camp"); Weekly plan and Phase 5 weeks 45-48.
- **What's wrong:** only three sessions are numbered (45, 46, 48). Camp 2 in week 46 is 40 minutes of training before the season review, awards and social. Camp 3 is a 90-minute session in the 1s' taper week, although the 2s have nothing to taper for. Week 47 is spent as the 1s' rehearsal opposition, with one line of feedback. The 2s' awards happen in the middle of their camp and five weeks before the club's.
- **Goal it hurts:** "every player leaves the August step-up camp with a plan for 2028/29"; "at least 2 players move up"; commitment 6 (2s goals celebrated alongside the 1s).
- **Fix:** four full camp sessions. Week 47 becomes camp 3: the rehearsal game is run as a test of each player's focus, with a 1s player or guest watching each 2s player. Weeks 46 and 48 get full training time.
- **Who:** Part 3. Moving the 2s' awards is Decision D13.

### 9. Trial 1 uses a game the club has never played

- **Where:** Phase 2 week 18; Season plan, Phase by phase ("trials use the same games").
- **What's wrong:** Variable stall count is listed as a familiar game at Trial 1. Its first appearance anywhere in the plan is Trial 1 (then weeks 21 and 40). Returning players and trialists are equally new to it, which is fair, but it is not what the plan promises, and the retention it tests has had no game since October.
- **Goal it hurts:** "squads picked fairly"; the promise that trials reward improvement in games the club knows.
- **Fix:** play Variable stall count in week 14 (the restart week on resets), where it also replaces a 40-minute drill block.
- **Who:** Part 3.

### 10. Week 30 is a full training week for a squad with a tournament that weekend

- **Where:** Weekly plan, Phase 3 ("Every event week is light"); Phase 3 week 30.
- **What's wrong:** week 30 (EUCS Spring, 1s) has a full 3-hour joint session and a full 1s split with 4v4 conditioning and a scrimmage. It sits between Herdlodge (games on Saturday and Sunday) and Tour 2, so the 1s play on three weekends running with no light week.
- **Goal it hurts:** the plan's own load rule; Nationals (injuries); Tour 2 performance.
- **Fix:** the 1s' week 30 split becomes a 90-minute walk-through with no conditioning. The joint session keeps the wind theme at 2.5 hours, and players going to EUCS sit out the last game.
- **Who:** Part 3.

### 11. The hard-leg rule can't be applied because the plan never names the training days

- **Where:** Season plan, Weekly structure and Fitness ("Hard leg sessions should not fall on consecutive days").
- **What's wrong:** nothing says which days the joint and split sessions are on. If they fall on consecutive days, every week breaks the rule. Home strength can't be placed either.
- **Goal it hurts:** Nationals; player availability all season.
- **Fix:** the programme is written with rules instead of days (never the day before a session or an event; a clear day between the two home sessions).
- **Who:** Part 2. Confirming the days is Decision D14.

### 12. The joint session has consequences in three places

- **Where:** Phase 2 week 24 (trade-off drill: "Hildo's push-ups swapped for short sprints"); Phase 3 week 36 and Phase 4 week 40 (Retention game: "costs the team a sprint").
- **What's wrong:** How we coach says "The joint session has no consequences; it stays the welcoming session for the 2s and newcomers", and that consequences never follow errors in the skill being learned. A throw to a covered receiver in a retention game is the skill being learned.
- **Goal it hurts:** Principle 5 (fun); recruitment and the 2s' welcome.
- **Fix:** score these games with points instead (the defence scores for a throw to a covered player).
- **Who:** Part 3.

### 13. Reviews are missing after three events

- **Where:** Phase 3 week 31 (no review of EUCS Spring, although the calendar lists "Event review (1s)"); Phase 5 week 45 (the table has a Regionals fix but no review slot); Phase 5 week 51 (no Nationals review on the pitch).
- **What's wrong:** "review and fix after every event" holds for Solent, Tours 1-3 and Regionals (a quick version). It is not in the tables for EUCS Spring, the full Regionals and EUCS Summer review, or Nationals.
- **Goal it hurts:** "Build the playbook through test events"; the event loop.
- **Fix:** a 10-minute review row in weeks 31 (1s, in the walk-through), 45 and 51.
- **Who:** Part 3.

### 14. Nothing prepares throwers for wind before "a very windy Tour 1"

- **Where:** Phase 3 weeks 25-26 and 30; Season plan, Throwing outside training (wind is "Phases 3-4").
- **What's wrong:** the defence block before Tour 1 is right. But throwing in wind is first trained in week 30, a month after the windy event, and the home routine reaches wind after Tour 1 too.
- **Goal it hurts:** "fewer turnovers per point than 2026/27"; Tour 1 as a useful test.
- **Fix:** the week 25 skill floor and the week 26 throwing block run into, with and across the wind, and the home throwing track brings wind forward to week 23.
- **Who:** Part 3 and Part 2.

### 15. Late sessions don't say how long they are

- **Where:** split tables in weeks 39, 40, 45 and 46 (last row at 2:00); joint tables in weeks 28, 36, 39, 46, 47 and 51.
- **What's wrong:** Phase 4 says sessions get "shorter and sharper", but only week 41 states a length. The app runs the last row to the end of the booked slot, so the week 47 "Recap" becomes 40 minutes and the week 39 split scrimmage an hour. Event weeks 37, 42, 43, 44, 48 and 49 are bullet lists, so the app builds no session for them.
- **Goal it hurts:** plans that anyone can step in and run; the taper (a taper week with no stated length drifts long).
- **Fix:** state the length in the label of every shorter session and give the light weeks timed tables.
- **Who:** Part 3. (This changes one test's expected value: see the summary.)

### 16. Parts of the curriculum never reach a session

- **Where:** Season plan, Skills curriculum.
- **What's wrong:**
  - **Jedi** (retention, Phases 3-4) and the "Jedi lanes game" are in the curriculum and the vocabulary. No session trains them.
  - **"Throwing tired"** (throwing base, Phase 2) is not in any session.
  - **"Throwing progressions per role"** (reading the pitch, Phases 3-4) is not in any session.
  - **Ladder climb** and the **jam drill** are named as key games and never used.
  - **Honeypass** has two different rule sets: a bonus for a set pair (drill library, Season plan) and "keep a shape and pass through set zones" (week 6).
- **Goal it hurts:** the promise that each area grows from technique to pressure to team use; "keeping the disc".
- **Fix:** a Jedi lanes game (described in full) in week 36; a throw-tired set after the 4v4 block in Phase 2; role progressions in the week 38 Plan A walk-through; one set of Honeypass rules; drop Ladder climb and jam drill from the "key games" cell only if the captains agree (they stay for now).
- **Who:** Part 3.

### 17. The same game comes back unchanged

- **Where:** Break-throw bonus point (weeks 10, 15, 16, 19, 32, 38, 46); Retention game (weeks 36 and 40, identical); Blocks Only (weeks 8, 20, 24, 25, 39); Asymmetric offence (weeks 1, 14, 17, 18).
- **What's wrong:** repeating key games is the plan's intent. But the tables give the same rule each time, so the game doesn't get harder as the players get better. That is repetition that goes nowhere.
- **Goal it hurts:** the technique-to-pressure-to-team progression; fun.
- **Fix:** each return states what has changed. For example, the break bonus goes from any break-side goal (week 10) to a break throw (15), to a break and a continuation within two throws (32), to the same at stall 5 (38).
- **Who:** Part 3.

### 18. Every 2028 event date falls on a weekday

- **Where:** every "~" date in the Season plan, Season at a glance, Weekly plan and Phase tabs.
- **What's wrong:** the dates are 2026's weekends carried forward. In 2028 they are Tuesdays (28 March, 2 May, 13 June, 18 July and 5 September 2028 are all Tuesdays). Each event could be the weekend before or after. The week table assumes the weekend after. If UKU uses the weekend before, every event comes a week earlier than the plan trains for, and the Tour 1 defence block loses a week.
- **Goal it hurts:** session content matching the calendar.
- **Fix:** none yet. No 2028 dates are published, so the estimates stay.
- **Who:** Decision D1.

### 19. Smaller mismatches between tabs

All fixed in Part 3 unless marked.

- **Drills by phase and source:** the Phase 5 summary still says the 2s "finish with end-of-season games and awards" (no step-up camp). The index lists Golden Arm and Honeypass in week 45, and the extended mark and quick-throw pairs in week 45; none is in the week 45 tables. Hockey Endzone is listed as "not yet used" but is round 5 in week 11.
- **Week 32:** the theme and learning point 2 name the extended mark; the joint table doesn't contain it.
- **Week 3:** nine activities before the water break, three of them 5-8 minutes long.
- **Week 27:** "Fix 1" is a drill and a game in 20 minutes; fix weeks need one fix per block.
- **Phase 1 intro:** dates say "to 17 December"; the phase table says 19 December.
- **Phase 3 intro:** calls the phase "Event-build"; every other tab says "Early season".
- **Classroom sessions:** "none in a tournament week" is not true of C7 (Herdlodge), and C1's on-pitch link is the same week, not the following one. Wording corrected.
- **Season at a glance, milestones:** "Weeks 45-48 2s step-up camp" now notes the camp tests.
- **Fitness table:** "Plyometrics... Phases 2-4" disagrees with "plyometrics... peak about 2-3 weeks before Nationals". Aligned to the programme in Part 2.
